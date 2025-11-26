from __future__ import annotations

import io
import logging
import time
import uuid
from datetime import datetime
from typing import Optional

import boto3
import requests
from fastapi import APIRouter, Depends, HTTPException, status as http_status
from fastapi.concurrency import run_in_threadpool

from utils.get_current_user_cognito import TokenData, get_current_user
from core.config import settings
from services.s3_service.deps import get_s3_storage
from services.s3_service.functions import S3Storage

from .deps import get_transcription_repository
from .repository import TranscriptionStatusRepository
from .schemas import (
    RecordingItem,
    RecordingListResponse,
    TranscriptionContentResponse,
    TranscriptionStartResponse,
    TranscriptionStatusResponse,
)
from .utils import (
    DEFAULT_STATUS,
    STATUS_COMPLETED,
    STATUS_ERROR,
    STATUS_IN_PROGRESS,
    build_transcription_key,
    decode_recording_id,
    encode_recording_id,
    extract_email_and_filename,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Transcriptions"])


async def _resolve_user_email(current_user: TokenData) -> str:
    email = current_user.email or current_user.username
    if not email:
        raise HTTPException(status_code=401, detail="Email claim missing in token")
    return email


def _merge_status(
    *,
    status_item: Optional[dict],
    transcription_exists: bool,
    transcription_key: str,
) -> tuple[str, Optional[str], Optional[datetime]]:
    if status_item:
        status = status_item.get("status", DEFAULT_STATUS)
        updated_at_raw = status_item.get("updated_at")
        updated_at = None
        if isinstance(updated_at_raw, (int, float)):
            updated_at = datetime.fromtimestamp(float(updated_at_raw))
        elif isinstance(updated_at_raw, str):
            try:
                updated_at = datetime.fromisoformat(updated_at_raw)
            except ValueError:
                updated_at = None
        # If Dynamo says completed but file missing, downgrade to pending
        if status == STATUS_COMPLETED and not transcription_exists:
            status = DEFAULT_STATUS
        return status, status_item.get("error_message"), updated_at

    # No record in Dynamo: infer status based on S3
    if transcription_exists:
        return STATUS_COMPLETED, None, None
    return DEFAULT_STATUS, None, None


def _guess_media_format(filename: str) -> Optional[str]:
    if "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext in {"mp3", "mp4", "wav", "flac", "m4a"}:
        return ext
    return None


def _transcribe_recording(
    *,
    recording_id: str,
    recording_key: str,
    transcription_key: str,
    repo: TranscriptionStatusRepository,
    s3: S3Storage,
    user_email: str,
    filename: str,
    poll_timeout_seconds: int = 300,
    poll_interval_seconds: int = 5,
) -> tuple[str, dict]:
    """Run a Transcribe job and persist the final text into S3 and DynamoDB."""

    transcribe_client = boto3.client("transcribe", region_name=settings.AWS_REGION)
    now_iso = datetime.utcnow().isoformat()
    base_item = {
        "recording_id": recording_id,
        "user_email": user_email,
        "transcription_key": transcription_key,
        "updated_at": now_iso,
    }

    repo.upsert_status({**base_item, "status": DEFAULT_STATUS})

    media_uri = f"s3://{s3.bucket}/{recording_key}"
    job_name = f"miwa-transcription-{uuid.uuid4().hex}"
    kwargs = {
        "TranscriptionJobName": job_name,
        "Media": {"MediaFileUri": media_uri},
        "IdentifyLanguage": True,
    }
    media_format = _guess_media_format(filename)
    if media_format:
        kwargs["MediaFormat"] = media_format

    transcribe_client.start_transcription_job(**kwargs)
    repo.upsert_status({**base_item, "status": STATUS_IN_PROGRESS, "job_name": job_name})

    deadline = time.time() + poll_timeout_seconds
    last_job: Optional[dict] = None
    while time.time() < deadline:
        job = transcribe_client.get_transcription_job(TranscriptionJobName=job_name)[
            "TranscriptionJob"
        ]
        last_job = job
        status = job["TranscriptionJobStatus"]
        if status == "COMPLETED":
            break
        if status == "FAILED":
            failure = job.get("FailureReason")
            repo.upsert_status(
                {**base_item, "status": STATUS_ERROR, "error_message": failure}
            )
            raise RuntimeError(f"Transcription failed: {failure}")
        time.sleep(poll_interval_seconds)

    if not last_job or last_job.get("TranscriptionJobStatus") != "COMPLETED":
        repo.upsert_status({**base_item, "status": STATUS_ERROR})
        raise RuntimeError("Transcription job did not complete before timeout")

    transcript_uri = last_job["Transcript"]["TranscriptFileUri"]
    resp = requests.get(transcript_uri, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    transcripts = payload.get("results", {}).get("transcripts", [])
    text_parts = [item.get("transcript", "") for item in transcripts if item.get("transcript")]
    transcription_text = "\n".join(text_parts).strip()
    if not transcription_text:
        # Fallback to raw payload if needed
        transcription_text = payload.get("text", "")

    buffer = io.BytesIO(transcription_text.encode("utf-8"))
    buffer.seek(0)
    s3.upload_fileobj(buffer, transcription_key, content_type="text/plain")

    completed_item = {
        **base_item,
        "status": STATUS_COMPLETED,
        "updated_at": datetime.utcnow().isoformat(),
    }
    repo.upsert_status(completed_item)
    return job_name, completed_item


@router.get("/recordings", response_model=RecordingListResponse)
async def list_user_recordings(
    current_user: TokenData = Depends(get_current_user),
    repo: TranscriptionStatusRepository = Depends(get_transcription_repository),
):
    user_email = await _resolve_user_email(current_user)
    s3: S3Storage = get_s3_storage()

    prefix = f"uploads/{user_email}/"
    try:
        recording_keys = await run_in_threadpool(
            lambda: s3.list_keys(prefix=prefix, max_items=1000)
        )
    except Exception as exc:  # pragma: no cover - network/aws failures
        logger.exception("Error listing user recordings")
        raise HTTPException(status_code=500, detail=str(exc))

    filtered_keys = []
    for key in recording_keys:
        relative = key.replace(prefix, "")
        if "/" in relative:
            continue
        filtered_keys.append(key)

    recording_ids = [encode_recording_id(key) for key in filtered_keys]

    try:
        statuses = await run_in_threadpool(repo.batch_get_statuses, recording_ids)
    except Exception as exc:  # pragma: no cover - network/aws failures
        logger.exception("Error fetching transcription status")
        raise HTTPException(status_code=500, detail="Unable to read transcription status")

    items: list[RecordingItem] = []
    for key, recording_id in zip(filtered_keys, recording_ids):
        _, filename = extract_email_and_filename(key)
        transcription_key = build_transcription_key(user_email, filename)

        try:
            transcription_exists = await run_in_threadpool(
                lambda: bool(s3.list_keys(prefix=transcription_key, max_items=1))
            )
        except Exception:
            transcription_exists = False

        status_item = statuses.get(recording_id)
        status, error_message, updated_at = _merge_status(
            status_item=status_item,
            transcription_exists=transcription_exists,
            transcription_key=transcription_key,
        )

        try:
            metadata = await run_in_threadpool(lambda: s3.get_object_metadata(key))
            uploaded_at = metadata.get("LastModified")
        except Exception:
            uploaded_at = None

        items.append(
            RecordingItem(
                recording_id=recording_id,
                file_name=filename,
                uploaded_at=uploaded_at,
                status=status,
                transcription_key=transcription_key if transcription_exists else None,
                transcription_ready=transcription_exists,
            )
        )

        # Optionally persist inferred completion for visibility in Dynamo
        if transcription_exists and (not status_item or status_item.get("status") != STATUS_COMPLETED):
            inferred_item = {
                "recording_id": recording_id,
                "status": STATUS_COMPLETED,
                "transcription_key": transcription_key,
                "user_email": user_email,
                "updated_at": datetime.utcnow().isoformat(),
            }
            try:
                await run_in_threadpool(repo.upsert_status, inferred_item)
            except Exception:
                logger.debug("Unable to persist inferred completion for %s", recording_id)

    return RecordingListResponse(items=items, total=len(items))


@router.post(
    "/transcriptions/{recording_id}/start",
    response_model=TranscriptionStartResponse,
    status_code=http_status.HTTP_202_ACCEPTED,
)
async def start_transcription(
    recording_id: str,
    current_user: TokenData = Depends(get_current_user),
    repo: TranscriptionStatusRepository = Depends(get_transcription_repository),
):
    s3: S3Storage = get_s3_storage()
    try:
        recording_key = decode_recording_id(recording_id)
        email_from_key, filename = extract_email_and_filename(recording_key)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid recording identifier")

    user_email = await _resolve_user_email(current_user)
    if email_from_key != user_email:
        raise HTTPException(
            status_code=403, detail="Access denied: recording does not belong to user"
        )

    transcription_key = build_transcription_key(user_email, filename)
    try:
        transcription_exists = await run_in_threadpool(
            lambda: bool(s3.list_keys(prefix=transcription_key, max_items=1))
        )
    except Exception:
        transcription_exists = False

    if transcription_exists:
        return TranscriptionStartResponse(
            recording_id=recording_id,
            status=STATUS_COMPLETED,
            transcription_key=transcription_key,
        )

    try:
        job_name, status_item = await run_in_threadpool(
            lambda: _transcribe_recording(
                recording_id=recording_id,
                recording_key=recording_key,
                transcription_key=transcription_key,
                repo=repo,
                s3=s3,
                user_email=user_email,
                filename=filename,
            )
        )
    except Exception as exc:  # pragma: no cover - AWS failures
        logger.exception("Error starting transcription job")
        raise HTTPException(status_code=500, detail=str(exc))

    updated_at = status_item.get("updated_at") if status_item else None
    parsed_updated_at: Optional[datetime] = None
    if isinstance(updated_at, str):
        try:
            parsed_updated_at = datetime.fromisoformat(updated_at)
        except ValueError:
            parsed_updated_at = None

    return TranscriptionStartResponse(
        recording_id=recording_id,
        status=status_item.get("status", STATUS_IN_PROGRESS) if status_item else STATUS_IN_PROGRESS,
        transcription_key=status_item.get("transcription_key") if status_item else None,
        updated_at=parsed_updated_at,
        job_name=job_name,
    )


@router.get(
    "/transcriptions/{recording_id}/status",
    response_model=TranscriptionStatusResponse,
)
async def get_transcription_status(
    recording_id: str,
    current_user: TokenData = Depends(get_current_user),
    repo: TranscriptionStatusRepository = Depends(get_transcription_repository),
):
    s3: S3Storage = get_s3_storage()
    try:
        key = decode_recording_id(recording_id)
        email_from_key, filename = extract_email_and_filename(key)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid recording identifier")

    user_email = await _resolve_user_email(current_user)
    if email_from_key != user_email:
        raise HTTPException(status_code=403, detail="Access denied: recording does not belong to user")

    transcription_key = build_transcription_key(user_email, filename)

    try:
        status_item = await run_in_threadpool(repo.get_status, recording_id)
    except Exception as exc:  # pragma: no cover - network/aws failures
        logger.exception("Error reading transcription status")
        raise HTTPException(status_code=500, detail="Unable to read transcription status")

    try:
        transcription_exists = await run_in_threadpool(
            lambda: bool(s3.list_keys(prefix=transcription_key, max_items=1))
        )
    except Exception:
        transcription_exists = False

    status, error_message, updated_at = _merge_status(
        status_item=status_item,
        transcription_exists=transcription_exists,
        transcription_key=transcription_key,
    )

    return TranscriptionStatusResponse(
        recording_id=recording_id,
        status=status,
        transcription_key=transcription_key if transcription_exists else None,
        updated_at=updated_at,
        error_message=error_message,
    )


@router.get("/transcriptions/{recording_id}", response_model=TranscriptionContentResponse)
async def get_transcription_content(
    recording_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    s3: S3Storage = get_s3_storage()
    try:
        key = decode_recording_id(recording_id)
        email_from_key, filename = extract_email_and_filename(key)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid recording identifier")

    user_email = await _resolve_user_email(current_user)
    if email_from_key != user_email:
        raise HTTPException(status_code=403, detail="Access denied: recording does not belong to user")

    transcription_key = build_transcription_key(user_email, filename)

    try:
        transcription_bytes = await run_in_threadpool(lambda: s3.download_as_bytes(transcription_key))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Transcription not found")
    except Exception as exc:  # pragma: no cover - network/aws failures
        logger.exception("Error reading transcription from S3")
        raise HTTPException(status_code=500, detail=str(exc))

    transcription_text = transcription_bytes.decode("utf-8", errors="replace")
    return TranscriptionContentResponse(
        recording_id=recording_id,
        transcription=transcription_text,
        transcription_key=transcription_key,
    )
