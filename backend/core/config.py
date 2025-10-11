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
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    DYNAMO_GOOGLE_TOKENS_TABLE: str
    GOOGLE_STATE_SECRET: str
    GOOGLE_AFTER_CONNECT: str

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

        return (
            f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


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
