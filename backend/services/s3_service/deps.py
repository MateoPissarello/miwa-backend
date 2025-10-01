"""Dependency helpers for the S3 plugin."""

from __future__ import annotations

from kernel import Kernel
from kernel.runtime import get_kernel

from .functions import S3Storage


CAPABILITY_NAME = "capability.storage.s3"


def register_s3_dependency(kernel: Kernel) -> None:
    """Expose the shared S3 storage capability through the kernel."""

    def _factory(k: Kernel) -> S3Storage:
        settings = k.settings
        return S3Storage(bucket=settings.S3_BUCKET_ARN, region=settings.AWS_REGION)

    kernel.register_capability(CAPABILITY_NAME, _factory)


def get_s3_storage() -> S3Storage:
    """FastAPI dependency used by routers to access the S3 storage service."""

    kernel = get_kernel()
    return kernel.resolve(CAPABILITY_NAME)
