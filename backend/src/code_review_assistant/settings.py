from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_db: str = Field(default="review_assistant", min_length=1)
    postgres_user: str = Field(default="review_assistant", min_length=1)
    postgres_password: SecretStr
    postgres_host: str = Field(default="127.0.0.1", min_length=1)
    postgres_port: int = Field(default=5432, ge=1, le=65535)

    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str | None = Field(default=None, min_length=1)

    github_app_id: int | None = Field(default=None, gt=0)
    github_private_key_path: Path | None = None
    github_webhook_secret: SecretStr | None = None
    github_webhook_enabled: bool = False

    review_provider: Literal["anthropic", "ollama"] = "anthropic"
    review_model: str | None = Field(default=None, min_length=1)

    embedding_provider: Literal["openai", "ollama"] = "openai"
    embedding_model: str | None = Field(default=None, min_length=1)
    embedding_dimensions: int = Field(default=1536, gt=0)

    ollama_base_url: str = Field(
        default="http://127.0.0.1:11434",
        min_length=1,
    )
