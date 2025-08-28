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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
