from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from app.core.config import Settings, get_settings
from app.repositories.mapping_repository import MappingRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.chat import CatalogSummaryResponse, ChatRequest, ChatResponse
from app.schemas.mapping import (
    DialogueTrainingLogResponse,
    MappingListResponse,
    MappingTrainRequest,
)
from app.services.condition_parser import ConditionParser
from app.services.dialogue_service import DialogueService
from app.services.longcat_client import LongCatClient
from app.services.recommendation_service import RecommendationService


router = APIRouter()

_dialogue_service: DialogueService | None = None
_product_repository: ProductRepository | None = None
_mapping_repository: MappingRepository | None = None


def get_product_repository(settings: Settings = Depends(get_settings)) -> ProductRepository:
    global _product_repository
    if _product_repository is None:
        _product_repository = ProductRepository(settings)
    return _product_repository


def get_mapping_repository(settings: Settings = Depends(get_settings)) -> MappingRepository:
    global _mapping_repository
    if _mapping_repository is None:
        _mapping_repository = MappingRepository(settings)
    return _mapping_repository


def get_dialogue_service(
    settings: Settings = Depends(get_settings),
    product_repository: ProductRepository = Depends(get_product_repository),
    mapping_repository: MappingRepository = Depends(get_mapping_repository),
) -> DialogueService:
    global _dialogue_service
    if _dialogue_service is None:
        longcat_client = LongCatClient(settings)
        condition_parser = ConditionParser(longcat_client, mapping_repository=mapping_repository)
        recommendation_service = RecommendationService(settings, product_repository)
        _dialogue_service = DialogueService(
            condition_parser=condition_parser,
            recommendation_service=recommendation_service,
            longcat_client=longcat_client,
            mapping_repository=mapping_repository,
        )
    return _dialogue_service


@router.get("/health", tags=["System"], summary="健康检查")
def health(settings: Settings = Depends(get_settings)) -> dict[str, str | bool]:
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "llm_enabled": settings.llm_enabled,
    }


@router.post(
    "/api/chat/message",
    response_model=ChatResponse,
    tags=["Chat"],
    summary="普通对话接口",
    description="一次性返回完整回复，适合后端联调和普通测试。",
)
async def chat_message(
    request: ChatRequest,
    dialogue_service: DialogueService = Depends(get_dialogue_service),
) -> ChatResponse:
    if not request.text.strip() and not request.image_urls:
        raise HTTPException(status_code=400, detail="text 和 image_urls 不能同时为空。")

    result = await dialogue_service.handle_message(
        session_id=request.session_id,
        text=request.text.strip() or "用户上传了图片",
        response_mode=request.response_mode,
    )
    return ChatResponse(session_id=request.session_id, **result)


@router.post(
    "/api/chat/stream",
    tags=["Chat"],
    summary="流式对话接口",
    description="使用 SSE 持续返回状态和回复片段，适合前端做流式展示。",
)
async def chat_stream(
    request: ChatRequest,
    dialogue_service: DialogueService = Depends(get_dialogue_service),
) -> StreamingResponse:
    if not request.text.strip() and not request.image_urls:
        raise HTTPException(status_code=400, detail="text 和 image_urls 不能同时为空。")

    async def event_generator():
        async for event in dialogue_service.stream_message(
            session_id=request.session_id,
            text=request.text.strip() or "用户上传了图片",
            response_mode=request.response_mode,
        ):
            yield _format_sse(event["type"], event.get("response") or {"text": event.get("text", "")})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post(
    "/api/admin/catalog/reload",
    response_model=CatalogSummaryResponse,
    tags=["Admin"],
    summary="重新加载货盘",
)
def reload_catalog(
    product_repository: ProductRepository = Depends(get_product_repository),
) -> CatalogSummaryResponse:
    product_repository.load_catalog(force_reload=True)
    return CatalogSummaryResponse(**product_repository.summary())


@router.get(
    "/api/admin/catalog/summary",
    response_model=CatalogSummaryResponse,
    tags=["Admin"],
    summary="查看货盘摘要",
)
def catalog_summary(
    product_repository: ProductRepository = Depends(get_product_repository),
) -> CatalogSummaryResponse:
    product_repository.load_catalog()
    return CatalogSummaryResponse(**product_repository.summary())


@router.get(
    "/api/admin/mappings",
    response_model=MappingListResponse,
    tags=["Mappings"],
    summary="查看当前训练映射",
)
def list_mappings(
    mapping_repository: MappingRepository = Depends(get_mapping_repository),
) -> MappingListResponse:
    return MappingListResponse(mappings=mapping_repository.list_mappings())


@router.post(
    "/api/admin/mappings/train",
    response_model=MappingListResponse,
    tags=["Mappings"],
    summary="新增一条训练映射",
)
def train_mapping(
    request: MappingTrainRequest,
    mapping_repository: MappingRepository = Depends(get_mapping_repository),
) -> MappingListResponse:
    mapping_repository.add_mapping(
        mapping_type=request.mapping_type,
        phrase=request.phrase,
        canonical_value=request.canonical_value,
    )
    return MappingListResponse(mappings=mapping_repository.list_mappings())


@router.get(
    "/api/admin/mappings/examples",
    response_model=DialogueTrainingLogResponse,
    tags=["Mappings"],
    summary="查看最近的对话训练样本",
)
def mapping_examples(
    mapping_repository: MappingRepository = Depends(get_mapping_repository),
) -> DialogueTrainingLogResponse:
    return DialogueTrainingLogResponse(
        examples=mapping_repository.recent_dialogue_examples(),
    )


@router.get(
    "/api/admin/diagnostics/llm",
    tags=["Admin"],
    summary="检查当前 LLM 连接状态",
)
async def llm_diagnostics(
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    result: dict[str, object] = {
        "llm_enabled": settings.llm_enabled,
        "model": settings.longcat_model,
        "api_url": settings.longcat_api_url,
        "chat_ok": False,
        "chat_reply_preview": "",
        "chat_error": None,
        "stream_ok": False,
        "stream_reply_preview": "",
        "stream_error": None,
    }

    if not settings.llm_enabled:
        result["chat_error"] = "LONGCAT_API_KEY 未配置"
        result["stream_error"] = "LONGCAT_API_KEY 未配置"
        return result

    client = LongCatClient(settings)
    payload = {"probe": "ping", "message": "请只回复 pong"}

    try:
        chat_reply = await client.chat_completion(
            system_prompt="You are a connectivity checker. Reply with pong only.",
            user_payload=payload,
            temperature=0,
            max_tokens=20,
        )
        result["chat_ok"] = True
        result["chat_reply_preview"] = chat_reply[:120]
    except Exception as exc:
        result["chat_error"] = str(exc)[:300]

    try:
        chunks: list[str] = []
        async for chunk in client.stream_chat_completion(
            system_prompt="You are a connectivity checker. Reply with pong only.",
            user_payload=payload,
            temperature=0,
            max_tokens=20,
        ):
            chunks.append(chunk)
            if len("".join(chunks)) >= 20:
                break
        result["stream_ok"] = bool("".join(chunks).strip())
        result["stream_reply_preview"] = "".join(chunks)[:120]
        if not result["stream_ok"]:
            result["stream_error"] = "流式调用未返回有效内容"
    except Exception as exc:
        result["stream_error"] = str(exc)[:300]

    return result


def _format_sse(event: str, data: dict) -> str:
    payload = json.dumps(jsonable_encoder(data), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
