"""Runtime configuration helpers for the MIWA backend."""

from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: str
    API_GATEWAY_URL: str
    COGNITO_USER_POOL_ID: str
    COGNITO_CLIENT_ID: str
    AWS_REGION: str
    COGNITO_SECRET: str
    S3_BUCKET_ARN: str
    BUCKET_NAME: str | None = None
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    DYNAMO_GOOGLE_TOKENS_TABLE: str
    GOOGLE_STATE_SECRET: str
    GOOGLE_AFTER_CONNECT: str
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: str
    DB_NAME: str
    DDB_TABLE_NAME: str = "meeting_artifacts"
    DEFAULT_URL_TTL_SEC: int = 3600
    TRANSCRIBE_LANG_HINT: str | None = None
    LLM_MODEL_ID: str = "amazon.titan-text-lite-v1"
    LLM_MAX_TOKENS: int = 4096
    ALLOW_EXTS: str = ".mp3,.mp4,.m4a,.wav"
    PIPELINE_STATE_MACHINE_ARN: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def COGNITO_ISSUER(self) -> str:
        return f"https://cognito-idp.{self.AWS_REGION}.amazonaws.com/{self.COGNITO_USER_POOL_ID}"

    @property
    def COGNITO_JWKS_URL(self) -> str:
        return f"{self.COGNITO_ISSUER}/.well-known/jwks.json"

    @property
    def DATABASE_URL(self) -> str:
        """Build the SQLAlchemy database URL from the configured credentials."""

        return f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def RECORDINGS_BUCKET_NAME(self) -> str:
        """Return the canonical bucket name used for meeting artefacts."""

        if self.BUCKET_NAME:
            return self.BUCKET_NAME
        bucket = self.S3_BUCKET_ARN
        if bucket.startswith("arn:"):
            if ":::" in bucket:
                bucket = bucket.split(":::")[-1]
            else:
                bucket = bucket.rsplit(":", 1)[-1]
        if bucket.startswith("s3://"):
            bucket = bucket[5:]
        if "/" in bucket:
            bucket = bucket.split("/", 1)[0]
        return bucket


_settings: Optional[Settings] = None


def set_settings(settings: Settings) -> None:
    """Set the singleton settings instance used across the application."""

    global _settings
    _settings = settings


def get_settings() -> Settings:
    """Return the active settings instance, loading it from the environment if needed."""

    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


class SettingsProxy:
    """Lazy proxy that defers attribute access to the active settings instance."""

    def __getattr__(self, item: str):  # type: ignore[override]
        return getattr(get_settings(), item)


settings = SettingsProxy()

__all__ = ["Settings", "get_settings", "set_settings", "settings"]
