from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import get_settings


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=(
        "钜盛珠宝智能体后端接口。\n\n"
        "推荐先从 Swagger UI 直接调试：\n"
        "- `/api/chat/message`：普通对话接口\n"
        "- `/api/chat/stream`：流式对话接口\n"
        "- `/api/admin/catalog/summary`：查看货盘摘要\n"
        "- `/api/admin/mappings`：查看训练映射\n"
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    swagger_ui_parameters={
        "docExpansion": "list",
        "defaultModelsExpandDepth": 1,
        "displayRequestDuration": True,
    },
)

static_dir = settings.backend_root / "data"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(router)
