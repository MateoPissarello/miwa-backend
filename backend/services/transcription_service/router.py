"""HTTP routes for meeting transcriptions management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import MeetingTranscript, User
from services.calendar_service import calendar_router as calendar_routes
from services.s3_service.deps import get_s3_storage
from services.s3_service.functions import S3Storage
from utils.get_current_user_cognito import TokenData, get_current_user

from .schemas import (
    TranscriptionCreatePayload,
    TranscriptionListResponse,
    TranscriptionResponse,
    TranscriptionSummaryResponse,
    TranscriptionView,
)


router = APIRouter(prefix="/transcriptions", tags=["Transcriptions"])


def _find_user(db: Session, current_user: TokenData) -> User:
    """Resolve the active SQL user from the authenticated token data."""

    if current_user.user_id is not None:
        user = db.query(User).filter(User.user_id == current_user.user_id).one_or_none()
        if user:
            return user

    if current_user.email:
        user = db.query(User).filter(User.email == current_user.email).one_or_none()
        if user:
            return user

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


def _presign_or_none(storage: S3Storage, key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    return storage.presign_get_url(key)


def _to_view(model: MeetingTranscript, storage: S3Storage) -> TranscriptionView:
    return TranscriptionView(
        id=model.id,
        calendar_event_id=model.calendar_event_id,
        calendar_summary=model.calendar_summary,
        recording_key=model.recording_key,
        status=model.status,
        started_at=model.started_at,
        updated_at=model.updated_at,
        recording_url=_presign_or_none(storage, model.recording_key),
        transcript_url=_presign_or_none(storage, model.transcript_key),
        summary_url=_presign_or_none(storage, model.summary_key),
    )


@router.get("/events")
async def list_transcription_events(
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Proxy calendar events from the last month for the authenticated user."""

    now = datetime.now(timezone.utc)
    time_min = now - timedelta(days=30)
    time_max = now
    iso_min = time_min.isoformat().replace("+00:00", "Z")
    iso_max = time_max.isoformat().replace("+00:00", "Z")

    return await calendar_routes.list_events(
        timeMin=iso_min,
        timeMax=iso_max,
        view=None,
        date_str=None,
        tz="UTC",
        pageToken=None,
        maxResults=200,
        calendarId="primary",
        current_user=current_user,
    )


@router.post("", response_model=TranscriptionResponse, status_code=status.HTTP_201_CREATED)
def create_or_update_transcription(
    payload: TranscriptionCreatePayload,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
    storage: S3Storage = Depends(get_s3_storage),
) -> TranscriptionResponse:
    user = _find_user(db, current_user)

    metadata = payload.metadata or {}

    transcript = (
        db.query(MeetingTranscript)
        .filter(
            MeetingTranscript.user_id == user.user_id,
            MeetingTranscript.calendar_event_id == payload.calendar_event_id,
        )
        .one_or_none()
    )

    now = datetime.utcnow()
    if transcript is None:
        transcript = MeetingTranscript(
            user_id=user.user_id,
            calendar_event_id=payload.calendar_event_id,
            status="uploaded",
            calendar_summary=payload.calendar_summary,
            started_at=payload.started_at,
            recording_key=payload.recording_key,
            transcript_key=payload.transcript_key or metadata.get("transcript_key"),
            summary_key=payload.summary_key or metadata.get("summary_key"),
            created_at=now,
            updated_at=now,
        )
        db.add(transcript)
    else:
        transcript.recording_key = payload.recording_key
        transcript.calendar_summary = payload.calendar_summary or transcript.calendar_summary
        transcript.started_at = payload.started_at or transcript.started_at
        if payload.transcript_key is not None or "transcript_key" in metadata:
            transcript.transcript_key = payload.transcript_key or metadata.get("transcript_key")
        if payload.summary_key is not None or "summary_key" in metadata:
            transcript.summary_key = payload.summary_key or metadata.get("summary_key")
        transcript.status = "uploaded"
        transcript.updated_at = now

    db.commit()
    db.refresh(transcript)

    view = _to_view(transcript, storage)
    return TranscriptionResponse(**view.model_dump(), created_at=transcript.created_at)


@router.get("", response_model=TranscriptionListResponse)
def list_transcriptions(
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
    storage: S3Storage = Depends(get_s3_storage),
) -> TranscriptionListResponse:
    user = _find_user(db, current_user)

    rows = (
        db.query(MeetingTranscript)
        .filter(MeetingTranscript.user_id == user.user_id)
        .order_by(MeetingTranscript.updated_at.desc())
        .all()
    )

    items = [_to_view(row, storage) for row in rows]
    return TranscriptionListResponse(items=items)


@router.get("/{transcription_id}/summary", response_model=TranscriptionSummaryResponse)
def get_transcription_summary(
    transcription_id: int,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
    storage: S3Storage = Depends(get_s3_storage),
) -> TranscriptionSummaryResponse:
    user = _find_user(db, current_user)

    transcript = (
        db.query(MeetingTranscript)
        .filter(
            MeetingTranscript.id == transcription_id,
            MeetingTranscript.user_id == user.user_id,
        )
        .one_or_none()
    )

    if transcript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcription not found")

    if not transcript.summary_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No summary available")

    url = storage.presign_get_url(transcript.summary_key)
    return TranscriptionSummaryResponse(
        id=transcript.id,
        summary_key=transcript.summary_key,
        summary_url=url,
    )
