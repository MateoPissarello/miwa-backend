"""Lambda-style handlers orchestrating the meeting processing pipeline."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from core.config import Settings

from .paths import MeetingS3Paths
from .repository import MeetingArtifactRepository
from .schemas import MeetingArtifactStatus, SummaryPayloadValidationError, validate_summary_payload


LOGGER = logging.getLogger(__name__)


def _settings() -> Settings:
    return Settings()


def _dynamo_repository(settings: Settings) -> MeetingArtifactRepository:
    client = boto3.client(
        "dynamodb",
        region_name=settings.AWS_REGION,
        config=Config(
            retries={"max_attempts": 10, "mode": "adaptive"},
            connect_timeout=5,
            read_timeout=10,
        ),
    )
    return MeetingArtifactRepository(client=client, table_name=settings.DDB_TABLE_NAME)


def _s3_client(settings: Settings):
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        config=Config(
            retries={"max_attempts": 5, "mode": "adaptive"},
            connect_timeout=5,
            read_timeout=30,
        ),
    )


def _transcribe_client(settings: Settings):
    return boto3.client(
        "transcribe",
        region_name=settings.AWS_REGION,
        config=Config(
            retries={"max_attempts": 5, "mode": "standard"},
            connect_timeout=5,
            read_timeout=30,
        ),
    )


def _bedrock_client(settings: Settings):
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.AWS_REGION,
        config=Config(
            retries={"max_attempts": 3, "mode": "adaptive"},
            connect_timeout=5,
            read_timeout=60,
        ),
    )


def _stepfunctions_client(settings: Settings):
    if not settings.PIPELINE_STATE_MACHINE_ARN:
        return None
    return boto3.client(
        "stepfunctions",
        region_name=settings.AWS_REGION,
        config=Config(
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=5,
            read_timeout=10,
        ),
    )


def _allowed_exts(settings: Settings) -> set[str]:
    return {ext.strip() for ext in settings.ALLOW_EXTS.split(",") if ext.strip()}


def _execution_name(paths: MeetingS3Paths) -> str:
    base = _sanitize_job_name(paths)
    return f"{base}-{uuid.uuid4().hex[:8]}"


def _sanitize_job_name(paths: MeetingS3Paths) -> str:
    components = [
        paths.identifier.user_email.replace("@", "-at-"),
        paths.identifier.meeting_name,
        paths.identifier.meeting_date,
        paths.identifier.basename,
    ]
    raw = "-".join(components)
    sanitized = "".join(ch.lower() if ch.isalnum() else "-" for ch in raw)
    sanitized = "-".join(filter(None, sanitized.split("-")))
    return sanitized[:200] if len(sanitized) > 200 else sanitized


def _mark_failed(
    repo: MeetingArtifactRepository,
    paths: MeetingS3Paths,
    *,
    error_code: str,
    error_message: str,
) -> None:
    repo.mark_failed(
        paths.identifier,
        error_code=error_code,
        error_message=error_message[:500],
    )


def _parse_s3_uri(uri: str) -> Tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme == "s3":
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        return bucket, key
    if parsed.scheme.startswith("http"):
        host_parts = parsed.netloc.split(".")
        if host_parts and host_parts[0] and host_parts[1].startswith("s3"):
            return host_parts[0], parsed.path.lstrip("/")
        path_parts = parsed.path.lstrip("/").split("/", 1)
        if len(path_parts) == 2:
            return path_parts[0], path_parts[1]
    raise ValueError(f"Unsupported transcript URI: {uri}")


def _transcript_segments(items: List[Dict[str, Any]], transcripts: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], float]:
    pronunciations = [item for item in items if item.get("type") == "pronunciation"]
    if pronunciations:
        start = float(pronunciations[0].get("start_time", 0.0))
        end = float(pronunciations[-1].get("end_time", pronunciations[-1].get("start_time", 0.0)))
    else:
        start = 0.0
        end = 0.0
    full_text = " ".join(t.get("transcript", "").strip() for t in transcripts if t.get("transcript")).strip()
    if not full_text:
        full_text = ""
    segment = {
        "start": start,
        "end": end,
        "speaker": "spk_0",
        "text": full_text,
    }
    duration = max(0.0, end - start)
    return [segment], duration


def _build_transcription_payload(
    raw: Dict[str, Any],
    *,
    language: str | None,
) -> Tuple[Dict[str, Any], float]:
    results = raw.get("results", {})
    items: List[Dict[str, Any]] = results.get("items", [])
    transcripts: List[Dict[str, Any]] = results.get("transcripts", [])
    segments, duration = _transcript_segments(items, transcripts)
    payload = {
        "language": language or results.get("language_code") or raw.get("language_code") or "unknown",
        "duration_sec": duration if duration else None,
        "segments": segments,
        "full_text": segments[0]["text"] if segments else "",
    }
    return payload, duration


def _truncate_text(text: str, max_chars: int = 12000) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _build_summary_prompt(paths: MeetingS3Paths, transcript_text: str, duration: float | None) -> str:
    identifier = paths.identifier
    duration_block = f"\nDuración (segundos): {duration:.2f}" if duration else ""
    transcript_excerpt = _truncate_text(transcript_text)
    return (
        "Eres un asistente que resume reuniones técnicas. A partir de la transcripción "
        "proporcionada debes generar un JSON válido con los campos: titulo, temas_tratados, "
        "resumen_general, pendientes (lista de objetos {descripcion, responsable?, fecha_limite?}), "
        "tags, acuerdos, riesgos y decisiones. Responde únicamente con JSON sin texto adicional.\n"
        f"Reunión: {identifier.meeting_name}\nFecha: {identifier.meeting_date}\n"
        f"Propietario: {identifier.user_email}{duration_block}\n\n"
        "Transcripción completa (usa esta información para el resumen):\n"
        f"{transcript_excerpt}"
    )


def ingest_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """Handle S3 ObjectCreated events for recordings uploads."""

    settings = _settings()
    repo = _dynamo_repository(settings)
    step_client = _stepfunctions_client(settings)
    processed: list[Dict[str, Any]] = []
    allowed_exts = _allowed_exts(settings)

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
        if step_client and settings.PIPELINE_STATE_MACHINE_ARN:
            execution_input = json.dumps({"recording_key": paths.recording_key})
            execution_name = _execution_name(paths)
            try:
                step_client.start_execution(
                    stateMachineArn=settings.PIPELINE_STATE_MACHINE_ARN,
                    name=execution_name,
                    input=execution_input,
                )
            except ClientError as exc:  # pragma: no cover - network interaction
                LOGGER.error("Failed to start pipeline execution", exc_info=True)
                _mark_failed(
                    repo,
                    paths,
                    error_code="PIPELINE_START_ERROR",
                    error_message=str(exc),
                )
                raise
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


def start_transcription_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    settings = _settings()
    repo = _dynamo_repository(settings)
    transcribe_client = _transcribe_client(settings)
    recording_key = event["recording_key"]
    paths = MeetingS3Paths.parse_from_recording_key(recording_key)
    job_name = f"{_sanitize_job_name(paths)}-{uuid.uuid4().hex[:6]}"
    job_args: Dict[str, Any] = {
        "TranscriptionJobName": job_name,
        "Media": {"MediaFileUri": f"s3://{settings.RECORDINGS_BUCKET_NAME}/{paths.recording_key}"},
        "MediaFormat": paths.ext.lstrip(".").lower(),
        "OutputBucketName": settings.RECORDINGS_BUCKET_NAME,
        "OutputKey": paths.transcription_output_prefix,
    }
    if settings.TRANSCRIBE_LANG_HINT:
        job_args["LanguageCode"] = settings.TRANSCRIBE_LANG_HINT
    else:
        job_args["IdentifyLanguage"] = True
    try:
        transcribe_client.start_transcription_job(**job_args)
    except ClientError as exc:  # pragma: no cover - network interaction
        LOGGER.error("Transcription job failed to start", exc_info=True)
        _mark_failed(
            repo,
            paths,
            error_code="TRANSCRIBE_START_ERROR",
            error_message=str(exc),
        )
        raise
    return {
        "recording_key": recording_key,
        "job_name": job_name,
        "status": "IN_PROGRESS",
    }


def poll_transcription_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    settings = _settings()
    repo = _dynamo_repository(settings)
    transcribe_client = _transcribe_client(settings)
    recording_key = event["recording_key"]
    job_name = event["job_name"]
    paths = MeetingS3Paths.parse_from_recording_key(recording_key)
    try:
        response = transcribe_client.get_transcription_job(TranscriptionJobName=job_name)
    except ClientError as exc:  # pragma: no cover
        LOGGER.error("Error retrieving transcription job", exc_info=True)
        _mark_failed(
            repo,
            paths,
            error_code="TRANSCRIBE_STATUS_ERROR",
            error_message=str(exc),
        )
        raise
    job = response.get("TranscriptionJob", {})
    status = job.get("TranscriptionJobStatus", "FAILED")
    if status == "FAILED":
        reason = job.get("FailureReason", "Unknown failure")
        _mark_failed(
            repo,
            paths,
            error_code="TRANSCRIBE_FAILED",
            error_message=reason,
        )
        return {
            "recording_key": recording_key,
            "job_name": job_name,
            "status": "FAILED",
        }
    if status != "COMPLETED":
        return {
            "recording_key": recording_key,
            "job_name": job_name,
            "status": "IN_PROGRESS",
        }
    transcript = job.get("Transcript", {})
    transcript_uri = transcript.get("TranscriptFileUri")
    language_code = job.get("LanguageCode")
    media = job.get("Media", {})
    media_format = job.get("MediaFormat")
    media_sample_rate = job.get("MediaSampleRateHertz")
    return {
        "recording_key": recording_key,
        "job_name": job_name,
        "status": "COMPLETED",
        "transcript_uri": transcript_uri,
        "language_code": language_code,
        "media_sample_rate_hz": media_sample_rate,
        "media_format": media_format,
        "media_uri": media.get("MediaFileUri"),
    }


def store_transcription_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    settings = _settings()
    repo = _dynamo_repository(settings)
    s3_client = _s3_client(settings)
    recording_key = event["recording_key"]
    transcript_uri = event["transcript_uri"]
    language_code = event.get("language_code")
    paths = MeetingS3Paths.parse_from_recording_key(recording_key)
    if not transcript_uri:
        _mark_failed(
            repo,
            paths,
            error_code="TRANSCRIBE_NO_OUTPUT",
            error_message="Transcribe job completed without transcript URI",
        )
        raise ValueError("Transcript URI missing from event")
    bucket, key = _parse_s3_uri(transcript_uri)
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        raw = json.loads(response["Body"].read())
    except Exception as exc:  # pragma: no cover - AWS interaction
        LOGGER.error("Failed to download transcription output", exc_info=True)
        _mark_failed(
            repo,
            paths,
            error_code="TRANSCRIBE_DOWNLOAD_ERROR",
            error_message=str(exc),
        )
        raise
    payload, duration = _build_transcription_payload(raw, language=language_code)
    artefact = transcribe_job(
        {
            "recording_key": recording_key,
            "transcription": payload,
            "duration_sec": duration if duration else None,
            "language": payload.get("language"),
        },
        _context,
    )
    return artefact


def generate_summary_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    settings = _settings()
    repo = _dynamo_repository(settings)
    s3_client = _s3_client(settings)
    recording_key = event["recording_key"]
    paths = MeetingS3Paths.parse_from_recording_key(recording_key)
    repo.update_status(paths.identifier, status=MeetingArtifactStatus.SUMMARIZING)
    try:
        response = s3_client.get_object(
            Bucket=settings.RECORDINGS_BUCKET_NAME,
            Key=paths.transcription_key,
        )
        transcription = json.loads(response["Body"].read())
    except Exception as exc:  # pragma: no cover - AWS interaction
        LOGGER.error("Unable to load transcription for summary", exc_info=True)
        _mark_failed(
            repo,
            paths,
            error_code="TRANSCRIPT_NOT_FOUND",
            error_message=str(exc),
        )
        raise
    transcript_text = transcription.get("full_text", "")
    duration = transcription.get("duration_sec")
    prompt = _build_summary_prompt(paths, transcript_text, duration)
    bedrock_client = _bedrock_client(settings)
    body = json.dumps(
        {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": settings.LLM_MAX_TOKENS,
                "temperature": 0.2,
                "topP": 0.9,
            },
        }
    )
    try:
        response = bedrock_client.invoke_model(modelId=settings.LLM_MODEL_ID, body=body)
        payload = json.loads(response["body"].read())
        results = payload.get("results", [])
        if not results:
            raise ValueError("Bedrock response missing results")
        output_text = results[0].get("outputText", "").strip()
        summary = json.loads(output_text)
        validate_summary_payload(summary)
    except SummaryPayloadValidationError as exc:
        LOGGER.error("Summary validation failed", exc_info=True)
        _mark_failed(
            repo,
            paths,
            error_code="LLM_INVALID_OUTPUT",
            error_message=str(exc),
        )
        raise
    except Exception as exc:  # pragma: no cover - network interaction
        LOGGER.error("Bedrock invocation failed", exc_info=True)
        _mark_failed(
            repo,
            paths,
            error_code="LLM_ERROR",
            error_message=str(exc),
        )
        raise
    artefact = summarize_job({"recording_key": recording_key, "summary": summary}, _context)
    return artefact


__all__ = [
    "ingest_handler",
    "transcribe_job",
    "summarize_job",
    "start_transcription_handler",
    "poll_transcription_handler",
    "store_transcription_handler",
    "generate_summary_handler",
]

