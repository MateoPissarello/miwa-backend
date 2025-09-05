from core.config import settings
from functools import lru_cache
from .functions import S3Storage


@lru_cache(maxsize=1)
def get_s3_storage() -> S3Storage:
    return S3Storage(bucket=settings.S3_BUCKET_ARN, region=settings.AWS_REGION)
