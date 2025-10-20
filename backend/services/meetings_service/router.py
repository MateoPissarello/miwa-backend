"""FastAPI router exposing the meetings REST API."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.config import settings
from services.s3_service.deps import get_s3_storage
from services.s3_service.functions import S3Storage
from utils.get_current_user_cognito import TokenData, get_current_user

from .deps import get_repository
from .paths import MeetingS3Paths
from .repository import MeetingArtifactRepository
from .schemas import MeetingArtifact, MeetingArtifactStatus, MeetingIdentifier


router = APIRouter(tags=["meetings"])


class MeetingListItem(BaseModel):
    nombre_reunion: str = Field(..., description="Nombre lógico de la reunión")
    archivo_url_presigned: Optional[str] = None
    nombre_archivo_grabacion: str
    estado_procesamiento: MeetingArtifactStatus
    summary_url_presigned: Optional[str] = None
    transcript_url_presigned: Optional[str] = None
    user_email: str
    meeting_name: str
    meeting_date: str
    basename: str


class MeetingListResponse(BaseModel):
    items: list[MeetingListItem]
    page: int
    page_size: int
    total: int


def _error(status_code: int, code: str, message: str, details: Optional[dict] = None) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message, "details": details or {}}},
    )


def _ensure_authorized(user: TokenData, user_email: str) -> None:
    if user.username != user_email:
        raise _error(403, "INVALID_INPUT", "user_email does not match authenticated user")


def _build_list_item(
    artefact: MeetingArtifact,
    s3: S3Storage,
    *,
    include_presigned: bool = True,
) -> MeetingListItem:
    paths = MeetingS3Paths(identifier=artefact.identifier, ext=artefact.ext)
    ttl = settings.DEFAULT_URL_TTL_SEC
    summary_url = None
    transcript_url = None
    if include_presigned:
        try:
            summary_url = (
                s3.presign_get_url(artefact.s3_key_summary, ttl)
                if artefact.s3_key_summary and artefact.status == MeetingArtifactStatus.SUMMARIZED
                else None
            )
        except Exception:  # pragma: no cover - presign failure is propagated lazily in endpoints
            summary_url = None
        try:
            transcript_url = (
                s3.presign_get_url(artefact.s3_key_transcription, ttl)
                if artefact.s3_key_transcription and artefact.status
                in {MeetingArtifactStatus.TRANSCRIBED, MeetingArtifactStatus.SUMMARIZED}
                else None
            )
        except Exception:
            transcript_url = None
        recording_url = s3.presign_get_url(paths.recording_key, ttl)
    else:
        recording_url = None
    return MeetingListItem(
        nombre_reunion=paths.folder,
        archivo_url_presigned=recording_url,
        nombre_archivo_grabacion=f"{artefact.identifier.basename}{artefact.ext}",
        estado_procesamiento=artefact.status,
        summary_url_presigned=summary_url,
        transcript_url_presigned=transcript_url,
        user_email=artefact.identifier.user_email,
        meeting_name=artefact.identifier.meeting_name,
        meeting_date=artefact.identifier.meeting_date,
        basename=artefact.identifier.basename,
    )


@router.get("/meetings", response_model=MeetingListResponse)
def list_meetings(
    *,
    user_email: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    meeting_name: Optional[str] = None,
    status: Optional[MeetingArtifactStatus] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: TokenData = Depends(get_current_user),
    repository: MeetingArtifactRepository = Depends(get_repository),
    s3: S3Storage = Depends(get_s3_storage),
) -> MeetingListResponse:
    if user_email is None:
        user_email = current_user.username
    _ensure_authorized(current_user, user_email)
    artefacts, total = repository.list_meetings(
        user_email=user_email,
        meeting_name=meeting_name,
        status=status,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )
    items = [_build_list_item(artefact, s3) for artefact in artefacts]
    return MeetingListResponse(items=items, page=page, page_size=page_size, total=total)


def _fetch_artifact_or_error(
    repository: MeetingArtifactRepository,
    *,
    user_email: str,
    meeting_name: str,
    meeting_date: str,
    basename: str,
) -> MeetingArtifact:
    identifier = MeetingIdentifier(
        user_email=user_email,
        meeting_name=meeting_name,
        meeting_date=meeting_date,
        basename=basename,
    )
    artefact = repository.get(identifier)
    if artefact is None:
        raise _error(404, "RESOURCE_NOT_FOUND", "Meeting artefact not found")
    return artefact


def _check_processing_state(artefact: MeetingArtifact) -> None:
    if artefact.status.is_processing:
        raise _error(409, "PROCESSING", "Processing is still in progress", {"status": artefact.status})
    if artefact.status == MeetingArtifactStatus.FAILED:
        raise _error(
            424,
            "FAILED",
            "Processing pipeline failed",
            {"error_code": artefact.error_code, "error_message": artefact.error_message},
        )


@router.get("/meetings/{user_email}/{meeting_name}/{meeting_date}/{basename}/summary")
def get_summary(
    user_email: str,
    meeting_name: str,
    meeting_date: str,
    basename: str,
    current_user: TokenData = Depends(get_current_user),
    repository: MeetingArtifactRepository = Depends(get_repository),
    s3: S3Storage = Depends(get_s3_storage),
):
    _ensure_authorized(current_user, user_email)
    artefact = _fetch_artifact_or_error(
        repository,
        user_email=user_email,
        meeting_name=meeting_name,
        meeting_date=meeting_date,
        basename=basename,
    )
    _check_processing_state(artefact)
    if artefact.status != MeetingArtifactStatus.SUMMARIZED or not artefact.s3_key_summary:
        raise _error(404, "RESOURCE_NOT_FOUND", "Summary not available")
    try:
        payload = json.loads(s3.download_as_bytes(artefact.s3_key_summary))
    except FileNotFoundError:
        raise _error(404, "RESOURCE_NOT_FOUND", "Summary file missing in storage")
    return payload


@router.get("/meetings/{user_email}/{meeting_name}/{meeting_date}/{basename}/transcript")
def get_transcript(
    user_email: str,
    meeting_name: str,
    meeting_date: str,
    basename: str,
    current_user: TokenData = Depends(get_current_user),
    repository: MeetingArtifactRepository = Depends(get_repository),
    s3: S3Storage = Depends(get_s3_storage),
):
    _ensure_authorized(current_user, user_email)
    artefact = _fetch_artifact_or_error(
        repository,
        user_email=user_email,
        meeting_name=meeting_name,
        meeting_date=meeting_date,
        basename=basename,
    )
    _check_processing_state(artefact)
    if artefact.s3_key_transcription is None:
        raise _error(404, "RESOURCE_NOT_FOUND", "Transcription not available")
    try:
        payload = json.loads(s3.download_as_bytes(artefact.s3_key_transcription))
    except FileNotFoundError:
        raise _error(404, "RESOURCE_NOT_FOUND", "Transcription file missing in storage")
    return payload


class PresignedUrlResponse(BaseModel):
    url: str
    expires_sec: int


@router.get(
    "/meetings/{user_email}/{meeting_name}/{meeting_date}/{basename}/recording-url",
    response_model=PresignedUrlResponse,
)
def get_recording_url(
    user_email: str,
    meeting_name: str,
    meeting_date: str,
    basename: str,
    expires_sec: Optional[int] = Query(None, ge=60, le=604800),
    current_user: TokenData = Depends(get_current_user),
    repository: MeetingArtifactRepository = Depends(get_repository),
    s3: S3Storage = Depends(get_s3_storage),
):
    _ensure_authorized(current_user, user_email)
    artefact = _fetch_artifact_or_error(
        repository,
        user_email=user_email,
        meeting_name=meeting_name,
        meeting_date=meeting_date,
        basename=basename,
    )
    _check_processing_state(artefact)
    ttl = expires_sec or settings.DEFAULT_URL_TTL_SEC
    paths = MeetingS3Paths(identifier=artefact.identifier, ext=artefact.ext)
    try:
        url = s3.presign_get_url(paths.recording_key, ttl)
    except FileNotFoundError:
        raise _error(404, "RESOURCE_NOT_FOUND", "Recording not found in storage")
    return PresignedUrlResponse(url=url, expires_sec=ttl)

