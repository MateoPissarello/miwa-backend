"""Domain logic for transcription state management."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy.orm import Session, sessionmaker

from core.config import Settings
from models import TranscriptionRecord, TranscriptionStatus
from services.s3_service.functions import S3Storage


class TranscriptionService:
    """High level API used by routers and background workers."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker,
        settings: Settings,
        storage: S3Storage,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._storage = storage

    @contextmanager
    def _session(self) -> Iterable[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------
    def create_or_update(
        self,
        *,
        recording_key: str,
        status: TranscriptionStatus,
        transcription_job_name: str | None,
    ) -> TranscriptionRecord:
        with self._session() as session:
            record = (
                session.query(TranscriptionRecord)
                .filter(TranscriptionRecord.recording_key == recording_key)
                .one_or_none()
            )
            if record is None:
                record = TranscriptionRecord(
                    recording_key=recording_key,
                    status=status,
                    transcription_job_name=transcription_job_name,
                )
                session.add(record)
                session.flush()
            else:
                record.status = status
                record.transcription_job_name = transcription_job_name
                record.updated_at = datetime.utcnow()
            session.refresh(record)
            return record

    def update_record(
        self,
        *,
        record_id: int,
        status: TranscriptionStatus | None = None,
        transcript_key: str | None = None,
        summary_key: str | None = None,
        transcript_text: str | None = None,
        summary_text: str | None = None,
        error_message: str | None = None,
        transcription_job_name: str | None = None,
    ) -> TranscriptionRecord:
        with self._session() as session:
            record = session.get(TranscriptionRecord, record_id)
            if record is None:
                raise ValueError("Transcription record not found")

            if status is not None:
                record.status = status
            if transcript_key is not None:
                record.transcript_key = transcript_key
            if summary_key is not None:
                record.summary_key = summary_key
            if transcript_text is not None:
                record.transcript_text = transcript_text
            if summary_text is not None:
                record.summary_text = summary_text
            if error_message is not None:
                record.error_message = error_message
            if transcription_job_name is not None:
                record.transcription_job_name = transcription_job_name
            record.updated_at = datetime.utcnow()
            session.flush()
            session.refresh(record)
            return record

    def list_records(self) -> list[TranscriptionRecord]:
        with self._session() as session:
            records = session.query(TranscriptionRecord).order_by(TranscriptionRecord.created_at.desc()).all()
            for record in records:
                session.expunge(record)
            return records

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def build_response_payload(self, record: TranscriptionRecord) -> dict[str, object]:
        def _maybe_url(key: Optional[str]) -> Optional[str]:
            if not key:
                return None
            return self._storage.presign_get_url(key)

        return {
            "id": record.id,
            "recording_key": record.recording_key,
            "recording_url": _maybe_url(record.recording_key),
            "transcript_key": record.transcript_key,
            "transcript_url": _maybe_url(record.transcript_key),
            "summary_key": record.summary_key,
            "summary_url": _maybe_url(record.summary_key),
            "status": record.status,
            "transcription_job_name": record.transcription_job_name,
            "transcript_text": record.transcript_text,
            "summary_text": record.summary_text,
            "error_message": record.error_message,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    @property
    def webhook_token(self) -> str:
        return self._settings.TRANSCRIPTION_WEBHOOK_TOKEN

