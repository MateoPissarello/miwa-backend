"""Pydantic schemas for the transcription API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from models import TranscriptionStatus


class TranscriptionCreateRequest(BaseModel):
    recording_key: str = Field(..., description="S3 key for the uploaded audio")
    status: TranscriptionStatus = Field(
        TranscriptionStatus.transcribing, description="Desired processing status"
    )
    transcription_job_name: Optional[str] = Field(
        default=None, description="Name of the AWS Transcribe job"
    )


class TranscriptionUpdateRequest(BaseModel):
    status: Optional[TranscriptionStatus] = None
    transcript_key: Optional[str] = None
    summary_key: Optional[str] = None
    transcript_text: Optional[str] = None
    summary_text: Optional[str] = None
    error_message: Optional[str] = None
    transcription_job_name: Optional[str] = None


class TranscriptionResponse(BaseModel):
    id: int
    recording_key: str
    recording_url: Optional[str]
    transcript_key: Optional[str]
    transcript_url: Optional[str]
    summary_key: Optional[str]
    summary_url: Optional[str]
    status: TranscriptionStatus
    transcription_job_name: Optional[str]
    transcript_text: Optional[str]
    summary_text: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

