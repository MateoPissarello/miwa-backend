"""Calendar plugin bundling integration and calendar routers."""

from __future__ import annotations

from kernel import Kernel, ServicePlugin

from .calendar_router import router as calendar_router
from .integration_router import router as integration_router


class CalendarPlugin(ServicePlugin):
    name = "calendar"

    def setup(self, kernel: Kernel) -> None:
        kernel.include_router(integration_router, prefix="/api")
        kernel.include_router(calendar_router, prefix="/api")


__all__ = ["CalendarPlugin"]
