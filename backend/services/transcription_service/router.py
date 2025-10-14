"""FastAPI router exposing the transcription endpoints."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Header, HTTPException, status

from .deps import get_transcription_service
from .schemas import (
    TranscriptionCreateRequest,
    TranscriptionResponse,
    TranscriptionUpdateRequest,
)
from .service import TranscriptionService


router = APIRouter(prefix="/transcriptions", tags=["transcriptions"])


def require_webhook_token(
    x_webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
    service: TranscriptionService = Depends(get_transcription_service),
) -> None:
    expected = service.webhook_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook token not configured",
        )
    if x_webhook_token != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook token")


@router.get("", response_model=List[TranscriptionResponse])
def list_transcriptions(service: TranscriptionService = Depends(get_transcription_service)):
    records = service.list_records()
    return [TranscriptionResponse(**service.build_response_payload(record)) for record in records]


@router.post(
    "",
    response_model=TranscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_webhook_token)],
)
def create_or_update_transcription(
    payload: TranscriptionCreateRequest,
    service: TranscriptionService = Depends(get_transcription_service),
):
    record = service.create_or_update(
        recording_key=payload.recording_key,
        status=payload.status,
        transcription_job_name=payload.transcription_job_name,
    )
    return TranscriptionResponse(**service.build_response_payload(record))


@router.patch(
    "/{transcription_id}",
    response_model=TranscriptionResponse,
    dependencies=[Depends(require_webhook_token)],
)
def update_transcription(
    transcription_id: int,
    payload: TranscriptionUpdateRequest,
    service: TranscriptionService = Depends(get_transcription_service),
):
    try:
        record = service.update_record(
            record_id=transcription_id,
            status=payload.status,
            transcript_key=payload.transcript_key,
            summary_key=payload.summary_key,
            transcript_text=payload.transcript_text,
            summary_text=payload.summary_text,
            error_message=payload.error_message,
            transcription_job_name=payload.transcription_job_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TranscriptionResponse(**service.build_response_payload(record))

