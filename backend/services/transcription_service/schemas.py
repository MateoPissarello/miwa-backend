"""Pydantic schemas for the transcription service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class TranscriptionCreatePayload(BaseModel):
    calendar_event_id: str
    recording_key: str
    calendar_summary: Optional[str] = None
    started_at: Optional[datetime] = None
    transcript_key: Optional[str] = None
    summary_key: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class TranscriptionView(BaseModel):
    id: int
    calendar_event_id: str
    calendar_summary: Optional[str] = None
    recording_key: Optional[str] = None
    status: str
    started_at: Optional[datetime] = None
    updated_at: datetime
    recording_url: Optional[str] = None
    transcript_url: Optional[str] = None
    summary_url: Optional[str] = None


class TranscriptionListResponse(BaseModel):
    items: list[TranscriptionView]


class TranscriptionResponse(TranscriptionView):
    created_at: datetime


class TranscriptionSummaryResponse(BaseModel):
    id: int
    summary_key: str
    summary_url: str
