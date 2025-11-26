"""Plugin that wires transcription endpoints and dependencies."""

from __future__ import annotations

from kernel import Kernel, ServicePlugin

from .deps import register_transcription_repository
from .router import router


class TranscriptionPlugin(ServicePlugin):
    name = "transcriptions"

    def setup(self, kernel: Kernel) -> None:
        register_transcription_repository(kernel)
        kernel.include_router(router, prefix="/api")


__all__ = ["TranscriptionPlugin"]
