"""Test configuration utilities shared across the backend suite."""

from __future__ import annotations

import os


_DEFAULT_ENV = {
    "SECRET_KEY": "test-secret-key",
    "ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "15",
    "API_GATEWAY_URL": "https://example.com/lambda-endpoint",
    "COGNITO_USER_POOL_ID": "us-east-1_test",
    "COGNITO_CLIENT_ID": "client-id",
    "AWS_REGION": "us-east-1",
    "COGNITO_SECRET": "dummy",
    "S3_BUCKET_ARN": "arn:aws:s3:::test-bucket",
    "GOOGLE_CLIENT_ID": "google-client",
    "GOOGLE_CLIENT_SECRET": "google-secret",
    "GOOGLE_REDIRECT_URI": "https://example.com/oauth2",
    "DYNAMO_GOOGLE_TOKENS_TABLE": "tokens-table",
    "GOOGLE_STATE_SECRET": "state-secret",
    "GOOGLE_AFTER_CONNECT": "https://example.com/after-connect",
    "DB_USER": "user",
    "DB_PASSWORD": "password",
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
    "DB_NAME": "miwa",
}


for _key, _value in _DEFAULT_ENV.items():
    os.environ.setdefault(_key, _value)
