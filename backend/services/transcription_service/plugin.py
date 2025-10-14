"""Transcription plugin wiring router dependencies into the kernel."""

from __future__ import annotations

from kernel import Kernel, ServicePlugin

from .router import router


class TranscriptionPlugin(ServicePlugin):
    name = "transcriptions"

    def setup(self, kernel: Kernel) -> None:
        kernel.include_router(router, prefix="/api")


__all__ = ["TranscriptionPlugin"]
