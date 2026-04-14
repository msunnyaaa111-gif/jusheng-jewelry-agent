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
    longcat_api_key: str = ""

    product_json_path: str = ""
    product_xlsx_path: str = ""
    default_budget_tolerance: float = 0.15
    expanded_budget_tolerance: float = 0.20
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
