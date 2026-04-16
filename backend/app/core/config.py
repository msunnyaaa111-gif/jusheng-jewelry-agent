from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "钜盛珠宝智能体后端"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    longcat_api_url: str = "https://api.longcat.chat/openai/v1/chat/completions"
    longcat_model: str = "LongCat-Flash-Chat"
    longcat_vision_model: str = ""
    longcat_api_key: str = ""

    product_json_path: str = ""
    product_xlsx_path: str = ""
    default_budget_tolerance: float = 0.15
    expanded_budget_tolerance: float = 0.20
    product_color_cache_path: str = ""
    user_chat_log_path: str = ""
    product_color_inference_limit: int = 24
    product_color_inference_concurrency: int = 4
    cors_allowed_origins: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def backend_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def project_root(self) -> Path:
        return self.backend_root.parent

    @property
    def llm_enabled(self) -> bool:
        return bool(self.longcat_api_key.strip())

    @property
    def cors_origins(self) -> list[str]:
        raw = self.cors_allowed_origins.strip()
        if not raw:
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    @property
    def effective_vision_model(self) -> str:
        return (self.longcat_vision_model or self.longcat_model).strip()

    @property
    def resolved_product_color_cache_path(self) -> Path:
        raw = self.product_color_cache_path.strip()
        if raw:
            return Path(raw)
        return self.backend_root / "data" / "product_color_cache.json"

    @property
    def resolved_user_chat_log_path(self) -> Path:
        raw = self.user_chat_log_path.strip()
        if raw:
            return Path(raw)
        return self.backend_root / "data" / "user_chat_logs.jsonl"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
