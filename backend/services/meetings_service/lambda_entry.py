"""Entry points for AWS Lambda functions wrapping meeting service handlers."""

from __future__ import annotations

from typing import Any, Dict

from . import handlers


def ingest(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    return handlers.ingest_handler(event, context)


def start_transcription(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    return handlers.start_transcription_handler(event, context)


def poll_transcription(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    return handlers.poll_transcription_handler(event, context)


def store_transcription(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    return handlers.store_transcription_handler(event, context)


def generate_summary(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    return handlers.generate_summary_handler(event, context)


def persist_transcription(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    return handlers.transcribe_job(event, context)


def persist_summary(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    return handlers.summarize_job(event, context)


__all__ = [
    "ingest",
    "start_transcription",
    "poll_transcription",
    "store_transcription",
    "generate_summary",
    "persist_transcription",
    "persist_summary",
]
