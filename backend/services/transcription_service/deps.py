"""Dependency helpers for the transcription tracking service."""

from __future__ import annotations

from kernel import Kernel
from kernel.runtime import get_kernel

from .repository import TranscriptionStatusRepository

CAPABILITY_NAME = "capability.transcriptions.repository"


def register_transcription_repository(kernel: Kernel) -> None:
    def _factory(k: Kernel) -> TranscriptionStatusRepository:
        settings = k.settings
        return TranscriptionStatusRepository(
            table_name=settings.DYNAMO_TRANSCRIPTIONS_TABLE,
            region=settings.AWS_REGION,
        )

    kernel.register_capability(CAPABILITY_NAME, _factory)


def get_transcription_repository() -> TranscriptionStatusRepository:
    kernel = get_kernel()
    return kernel.resolve(CAPABILITY_NAME)
