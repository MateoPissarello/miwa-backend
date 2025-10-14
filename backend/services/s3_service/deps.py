"""Dependency helpers for the S3 plugin."""

from __future__ import annotations

from kernel import Kernel
from kernel.runtime import get_kernel

from .functions import S3Storage


def _normalize_bucket_name(bucket_identifier: str) -> str:
    """Return a usable bucket name extracted from an ARN or URI string."""

    bucket = bucket_identifier.strip()
    if not bucket:
        raise ValueError("S3 bucket identifier cannot be empty")

    if bucket.startswith("arn:"):
        # Standard bucket ARNs look like ``arn:aws:s3:::bucket-name``.
        if ":::" in bucket:
            bucket = bucket.split(":::")[-1]
        else:
            bucket = bucket.rsplit(":", 1)[-1]
    elif bucket.startswith("s3://"):
        bucket = bucket[5:]
    # Remove any potential path component after the bucket name
    if "/" in bucket:
        bucket = bucket.split("/", 1)[0]

    if not bucket:
        raise ValueError("Could not determine S3 bucket name from identifier")

    return bucket


CAPABILITY_NAME = "capability.storage.s3"


def register_s3_dependency(kernel: Kernel) -> None:
    """Expose the shared S3 storage capability through the kernel."""

    def _factory(k: Kernel) -> S3Storage:
        settings = k.settings
        bucket_name = _normalize_bucket_name(settings.S3_BUCKET_ARN)
        return S3Storage(bucket=bucket_name, region=settings.AWS_REGION)

    kernel.register_capability(CAPABILITY_NAME, _factory)


def get_s3_storage() -> S3Storage:
    """FastAPI dependency used by routers to access the S3 storage service."""

    kernel = get_kernel()
    return kernel.resolve(CAPABILITY_NAME)
