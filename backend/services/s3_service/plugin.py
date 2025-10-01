"""S3 service plugin wiring its router and storage capability."""

from __future__ import annotations

from kernel import Kernel, ServicePlugin

from .deps import register_s3_dependency
from .router import router


class S3Plugin(ServicePlugin):
    name = "storage.s3"

    def setup(self, kernel: Kernel) -> None:
        register_s3_dependency(kernel)
        kernel.include_router(router, prefix="/api")


__all__ = ["S3Plugin"]
