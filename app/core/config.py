from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    app_name: str = Field(default="AI Chatbot", min_length=1)
    app_env: Literal["development", "test", "production"] = "development"

    db_host: str = Field(default="127.0.0.1", min_length=1)
    db_port: int = Field(default=5433, ge=1, le=65535)
    postgres_db: str = Field(min_length=1)
    postgres_user: str = Field(min_length=1)
    postgres_password: SecretStr = Field(min_length=1)

    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=0, ge=0, le=20)
    db_pool_timeout_seconds: float = Field(default=5.0, gt=0)
    db_connect_timeout_seconds: int = Field(default=5, ge=2)
    db_statement_timeout_ms: int = Field(default=5000, ge=1)
    db_health_timeout_seconds: float = Field(default=8.0, gt=0)
    embedding_provider: str = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimensions: int = Field(default=384, ge=1)
    embedding_threads: int = Field(default=2, ge=1, le=32)
    embedding_cache_dir: Path = PROJECT_ROOT / ".cache" / "fastembed"
    # MVP evidence heuristic, calibrated initially against local document queries.
    rag_max_cosine_distance: float = Field(default=0.45, ge=0, le=2, allow_inf_nan=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
