"""Kernel dependency registration for the transcription service."""

from __future__ import annotations

from kernel import Kernel
from kernel.runtime import get_kernel

from .service import TranscriptionService


CAPABILITY_NAME = "services.transcriptions.manager"


def register_transcription_service(kernel: Kernel) -> None:
    """Register the transcription service manager with the kernel."""

    def _factory(k: Kernel) -> TranscriptionService:
        session_factory = k.resolve("db_session_factory")
        settings = k.settings
        storage = k.resolve("capability.storage.s3")
        return TranscriptionService(
            session_factory=session_factory,
            settings=settings,
            storage=storage,
        )

    kernel.register_capability(CAPABILITY_NAME, _factory)


def get_transcription_service() -> TranscriptionService:
    kernel = get_kernel()
    return kernel.resolve(CAPABILITY_NAME)

