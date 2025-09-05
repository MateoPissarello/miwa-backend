from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: str
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: str
    DB_NAME: str
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


settings = Settings()
