from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RecordingItem(BaseModel):
    """Represents a user recording alongside its transcription status."""

    recording_id: str = Field(..., description="Opaque identifier for the uploaded file")
    file_name: str
    uploaded_at: Optional[datetime]
    status: str
    transcription_key: Optional[str] = Field(
        default=None, description="S3 key where the transcription is stored"
    )
    transcription_ready: bool = Field(
        default=False, description="Indicates whether the transcription file can be fetched"
    )


class RecordingListResponse(BaseModel):
    items: list[RecordingItem]
    total: int


class TranscriptionStatusResponse(BaseModel):
    recording_id: str
    status: str
    transcription_key: Optional[str] = None
    updated_at: Optional[datetime] = None
    error_message: Optional[str] = None


class TranscriptionContentResponse(BaseModel):
    recording_id: str
    transcription: str
    transcription_key: str


class TranscriptionStartResponse(BaseModel):
    recording_id: str
    status: str
    transcription_key: Optional[str] = None
    updated_at: Optional[datetime] = None
    job_name: Optional[str] = None
