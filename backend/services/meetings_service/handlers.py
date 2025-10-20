"""Lambda-style handlers orchestrating the meeting processing pipeline."""

from __future__ import annotations

import json
from typing import Any, Dict

import boto3
from botocore.config import Config

from core.config import Settings

from .paths import MeetingS3Paths
from .repository import MeetingArtifactRepository
from .schemas import MeetingArtifactStatus, validate_summary_payload


def _settings() -> Settings:
    return Settings()


def _dynamo_repository(settings: Settings) -> MeetingArtifactRepository:
    client = boto3.client(
        "dynamodb",
        region_name=settings.AWS_REGION,
        config=Config(retries={"max_attempts": 10, "mode": "adaptive"}, connect_timeout=5, read_timeout=10),
    )
    return MeetingArtifactRepository(client=client, table_name=settings.DDB_TABLE_NAME)


def _s3_client(settings: Settings):
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        config=Config(retries={"max_attempts": 5, "mode": "adaptive"}, connect_timeout=5, read_timeout=30),
    )


def ingest_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """Handle S3 ObjectCreated events for recordings uploads."""

    settings = _settings()
    repo = _dynamo_repository(settings)
    processed: list[Dict[str, Any]] = []
    allowed_exts = {ext.strip() for ext in settings.ALLOW_EXTS.split(",") if ext.strip()}

    for record in event.get("Records", []):
        s3_obj = record.get("s3", {})
        bucket_key = s3_obj.get("object", {}).get("key")
        if not bucket_key:
            continue
        paths = MeetingS3Paths.parse_from_recording_key(bucket_key)
        if allowed_exts and paths.ext not in allowed_exts:
            raise ValueError(f"Extension {paths.ext} not allowed")
        repo.upsert_recording(
            paths.identifier,
            ext=paths.ext,
            s3_key_recording=paths.recording_key,
            status=MeetingArtifactStatus.TRANSCRIBING,
        )
        processed.append({"pk": paths.identifier.compose_pk(), "status": MeetingArtifactStatus.TRANSCRIBING.value})
    return {"processed": processed}


def transcribe_job(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """Persist the transcription artefact and transition the meeting status."""

    settings = _settings()
    repo = _dynamo_repository(settings)
    s3_client = _s3_client(settings)
    recording_key = event["recording_key"]
    transcription = event["transcription"]
    paths = MeetingS3Paths.parse_from_recording_key(recording_key)
    payload_bytes = json.dumps(transcription).encode("utf-8")
    s3_client.put_object(
        Bucket=settings.RECORDINGS_BUCKET_NAME,
        Key=paths.transcription_key,
        Body=payload_bytes,
        ContentType="application/json",
    )
    artefact = repo.update_with_transcription(
        paths.identifier,
        s3_key_transcription=paths.transcription_key,
        status=MeetingArtifactStatus.TRANSCRIBED,
        duration_sec=event.get("duration_sec"),
        language=event.get("language"),
    )
    return {"pk": artefact.identifier.compose_pk(), "status": artefact.status.value}


def summarize_job(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """Persist the structured summary JSON and mark the meeting as summarized."""

    settings = _settings()
    repo = _dynamo_repository(settings)
    s3_client = _s3_client(settings)
    recording_key = event["recording_key"]
    summary = event["summary"]
    validate_summary_payload(summary)
    paths = MeetingS3Paths.parse_from_recording_key(recording_key)
    payload_bytes = json.dumps(summary).encode("utf-8")
    s3_client.put_object(
        Bucket=settings.RECORDINGS_BUCKET_NAME,
        Key=paths.summary_key,
        Body=payload_bytes,
        ContentType="application/json",
    )
    artefact = repo.update_with_summary(
        paths.identifier,
        s3_key_summary=paths.summary_key,
        status=MeetingArtifactStatus.SUMMARIZED,
    )
    return {"pk": artefact.identifier.compose_pk(), "status": artefact.status.value}


__all__ = ["ingest_handler", "transcribe_job", "summarize_job"]

