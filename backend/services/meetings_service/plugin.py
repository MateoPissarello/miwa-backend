"""Meetings service plugin wiring capabilities and routers."""

from __future__ import annotations

from kernel import Kernel, ServicePlugin

from . import deps
from .router import router


class MeetingsPlugin(ServicePlugin):
    """Register capabilities and API routes for meeting artefacts."""

    name = "meetings"

    def setup(self, kernel: Kernel) -> None:  # noqa: D401 - interface requirement
        deps.register_dependencies(kernel)
        kernel.include_router(router, prefix="/api/v1")


__all__ = ["MeetingsPlugin"]

