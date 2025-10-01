"""Authentication plugin wiring the existing routers into the kernel."""

from __future__ import annotations

from kernel import Kernel, ServicePlugin

from .cognito_router import router as cognito_router
from .router import router as auth_router


class AuthPlugin(ServicePlugin):
    name = "auth"

    def setup(self, kernel: Kernel) -> None:
        kernel.include_router(auth_router, prefix="/api")
        kernel.include_router(cognito_router, prefix="/api")


__all__ = ["AuthPlugin"]
