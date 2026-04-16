from __future__ import annotations

import json
import logging
from time import perf_counter

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from app.core.config import Settings, get_settings
from app.repositories.chat_log_repository import ChatLogRepository
from app.repositories.mapping_repository import MappingRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.chat import CatalogSummaryResponse, ChatRequest, ChatResponse
from app.schemas.logs import ChatLogListResponse
from app.schemas.mapping import (
    DialogueTrainingLogResponse,
    MappingListResponse,
    MappingTrainRequest,
)
from app.services.condition_parser import ConditionParser
from app.services.dialogue_service import DialogueService
from app.services.longcat_client import LongCatClient
from app.services.product_color_inference_service import ProductColorInferenceService
from app.services.recommendation_service import RecommendationService


router = APIRouter()
logger = logging.getLogger(__name__)

_dialogue_service: DialogueService | None = None
_product_repository: ProductRepository | None = None
_mapping_repository: MappingRepository | None = None
_chat_log_repository: ChatLogRepository | None = None


async def _build_http_error_detail(exc: Exception) -> dict[str, object]:
    detail: dict[str, object] = {
        "type": exc.__class__.__name__,
        "message": str(exc)[:500],
    }

    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        body_preview = ""
        try:
            body_preview = exc.response.text[:1000]
        except Exception:
            try:
                body_preview = (await exc.response.aread()).decode("utf-8", errors="replace")[:1000]
            except Exception:
                body_preview = ""

        detail.update(
            {
                "status_code": exc.response.status_code,
                "url": str(exc.request.url) if exc.request is not None else None,
                "body_preview": body_preview,
            }
        )
    elif isinstance(exc, httpx.RequestError):
        detail.update(
            {
                "url": str(exc.request.url) if exc.request is not None else None,
            }
        )

    return detail


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


def get_chat_log_repository(settings: Settings = Depends(get_settings)) -> ChatLogRepository:
    global _chat_log_repository
    if _chat_log_repository is None:
        _chat_log_repository = ChatLogRepository(settings)
    return _chat_log_repository


def get_dialogue_service(
    settings: Settings = Depends(get_settings),
    product_repository: ProductRepository = Depends(get_product_repository),
    mapping_repository: MappingRepository = Depends(get_mapping_repository),
) -> DialogueService:
    global _dialogue_service
    if _dialogue_service is None:
        longcat_client = LongCatClient(settings)
        condition_parser = ConditionParser(longcat_client, mapping_repository=mapping_repository)
        color_inference_service = ProductColorInferenceService(settings, longcat_client)
        recommendation_service = RecommendationService(
            settings,
            product_repository,
            color_inference_service=color_inference_service,
        )
        _dialogue_service = DialogueService(
            condition_parser=condition_parser,
            recommendation_service=recommendation_service,
            longcat_client=longcat_client,
            mapping_repository=mapping_repository,
        )
    return _dialogue_service


def _log_chat_turn(
    *,
    chat_log_repository: ChatLogRepository,
    request: ChatRequest,
    response_payload: dict[str, object],
    duration_ms: int | None,
    status: str = "ok",
    error_message: str | None = None,
) -> None:
    chat_log_repository.append_log(
        session_id=request.session_id,
        user_id=request.user_id,
        request_text=request.text.strip(),
        image_urls=list(request.image_urls),
        response_mode=request.response_mode,
        response=response_payload,
        duration_ms=duration_ms,
        status=status,
        error_message=error_message,
    )


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
    chat_log_repository: ChatLogRepository = Depends(get_chat_log_repository),
) -> ChatResponse:
    if not request.text.strip() and not request.image_urls:
        raise HTTPException(status_code=400, detail="text 和 image_urls 不能同时为空。")

    started_at = perf_counter()
    result = await dialogue_service.handle_message(
        session_id=request.session_id,
        text=request.text.strip() or "用户上传了图片",
        response_mode=request.response_mode,
    )
    response = ChatResponse(session_id=request.session_id, **result)
    _log_chat_turn(
        chat_log_repository=chat_log_repository,
        request=request,
        response_payload=jsonable_encoder(response),
        duration_ms=int((perf_counter() - started_at) * 1000),
    )
    return response


@router.post(
    "/api/chat/stream",
    tags=["Chat"],
    summary="流式对话接口",
    description="使用 SSE 持续返回状态和回复片段，适合前端做流式展示。",
)
async def chat_stream(
    request: ChatRequest,
    dialogue_service: DialogueService = Depends(get_dialogue_service),
    chat_log_repository: ChatLogRepository = Depends(get_chat_log_repository),
) -> StreamingResponse:
    if not request.text.strip() and not request.image_urls:
        raise HTTPException(status_code=400, detail="text 和 image_urls 不能同时为空。")

    started_at = perf_counter()

    async def event_generator():
        try:
            async for event in dialogue_service.stream_message(
            session_id=request.session_id,
            text=request.text.strip() or "用户上传了图片",
            response_mode=request.response_mode,
        ):
                if event["type"] == "done" and event.get("response"):
                    _log_chat_turn(
                        chat_log_repository=chat_log_repository,
                        request=request,
                        response_payload=jsonable_encoder(event["response"]),
                        duration_ms=int((perf_counter() - started_at) * 1000),
                    )
                yield _format_sse(event["type"], event.get("response") or {"text": event.get("text", "")})
        except Exception:
            logger.exception("Streaming chat response failed", extra={"session_id": request.session_id})
            fallback_response = ChatResponse(
                session_id=request.session_id,
                action="GENERAL_REPLY",
                reply_text="这一轮生成中途出现了异常，商品卡片没有完整返回。您可以直接再发一次，我会按最新条件继续为您整理。",
                reply_source="stream_fallback",
                purchase_advice=None,
                followup_question=None,
                recommended_products=[],
                session_state=dialogue_service.get_session_state(request.session_id),
            )
            _log_chat_turn(
                chat_log_repository=chat_log_repository,
                request=request,
                response_payload=jsonable_encoder(fallback_response),
                duration_ms=int((perf_counter() - started_at) * 1000),
                status="stream_fallback",
                error_message="streaming chat response failed",
            )
            yield _format_sse("done", fallback_response.model_dump())

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
    "/api/admin/chat-logs",
    response_model=ChatLogListResponse,
    tags=["Admin"],
    summary="查看用户对话日志",
)
def chat_logs(
    session_id: str | None = Query(default=None, description="Filter by session ID."),
    user_id: str | None = Query(default=None, description="Filter by user ID."),
    keyword: str | None = Query(default=None, description="Keyword search in request, reply, or product names."),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of log records."),
    chat_log_repository: ChatLogRepository = Depends(get_chat_log_repository),
) -> ChatLogListResponse:
    return ChatLogListResponse(
        logs=chat_log_repository.recent_logs(
            limit=limit,
            session_id=session_id,
            user_id=user_id,
            keyword=keyword,
        )
    )


@router.get(
    "/api/admin/diagnostics/llm",
    tags=["Admin"],
    summary="检查当前 LLM 连接状态",
)
async def llm_diagnostics(
    settings: Settings = Depends(get_settings),
    model: str | None = Query(default=None, description="Optional model override for diagnostics."),
    temperature: float = Query(default=0.4, description="Probe temperature override."),
) -> dict[str, object]:
    effective_model = model or settings.longcat_model
    result: dict[str, object] = {
        "llm_enabled": settings.llm_enabled,
        "model": settings.longcat_model,
        "effective_model": effective_model,
        "effective_temperature": temperature,
        "api_url": settings.longcat_api_url,
        "probe_payload": {"probe": "ping", "message": "请只回复 pong"},
        "chat_ok": False,
        "chat_reply_preview": "",
        "chat_error": None,
        "chat_error_detail": None,
        "stream_ok": False,
        "stream_reply_preview": "",
        "stream_error": None,
        "stream_error_detail": None,
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
            temperature=temperature,
            max_tokens=20,
            model=effective_model,
        )
        result["chat_ok"] = True
        result["chat_reply_preview"] = chat_reply[:120]
    except Exception as exc:
        result["chat_error"] = str(exc)[:300]
        result["chat_error_detail"] = await _build_http_error_detail(exc)

    try:
        chunks: list[str] = []
        async for chunk in client.stream_chat_completion(
            system_prompt="You are a connectivity checker. Reply with pong only.",
            user_payload=payload,
            temperature=temperature,
            max_tokens=20,
            model=effective_model,
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
        result["stream_error_detail"] = await _build_http_error_detail(exc)

    return result


def _format_sse(event: str, data: dict) -> str:
    payload = json.dumps(jsonable_encoder(data), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
