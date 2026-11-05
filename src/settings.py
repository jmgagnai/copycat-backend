from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")
    LOG_LEVEL: str = "INFO"
    PORT: int = 3000
    DATABASE_URL: str
    ADMIN_EMAILS: str
    OPENROUTER_API_KEY: str

    OPENROUTER_MODEL_METADATA: str
    OPENROUTER_MODEL_SECTION_SUMMARY: str
    OPENROUTER_MODEL_CHAT_SNIPPET: str
    OPENROUTER_MODEL_EXECUTIVE_SUMMARY: str
    OPENROUTER_MODEL_ABSTRACT: str
    OPENROUTER_MODEL_CHAT_ANSWER: str
    OPENROUTER_MODEL_EMBEDDING: str

    DOCLING_IMAGE: str = "ghcr.io/docling-project/docling-serve-cpu:v1.1.0"
    DOCLING_TIMEOUT_MS: int = 60 * 60_000
    DOCLING_TABLE_MODE: str = "fast"
    DOCKER_BIN: str = "docker"

    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    DOCUMENTS_BUCKET: str

    @property
    def postgres_dsn(self) -> str:
        return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    @property
    def administrators(self) -> set[str]:
        return {e.strip().lower() for e in self.ADMIN_EMAILS.split(",") if e.strip()}


settings = Settings()  # pyright: ignore[reportCallIssue]  # fields come from .env
