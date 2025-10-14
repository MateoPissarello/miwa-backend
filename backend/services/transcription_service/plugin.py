"""Transcription service plugin registration."""

from __future__ import annotations

from kernel import Kernel, ServicePlugin

from .deps import register_transcription_service
from .router import router


class TranscriptionPlugin(ServicePlugin):
    name = "services.transcriptions"

    def setup(self, kernel: Kernel) -> None:
        register_transcription_service(kernel)
        kernel.include_router(router, prefix="/api")


__all__ = ["TranscriptionPlugin"]

