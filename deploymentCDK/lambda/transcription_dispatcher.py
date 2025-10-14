"""Lambda handler triggered by audio uploads to dispatch transcription jobs."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, Tuple

import boto3


CONFIG_SECRET_ARN = os.environ.get("CONFIG_SECRET_ARN", "")
API_BASE_URL = os.environ.get("API_BASE_URL", "").rstrip("/")
RAW_TRANSCRIPTS_PREFIX = os.environ.get("RAW_TRANSCRIPTS_PREFIX", "transcripts/raw/")
WEBHOOK_HEADER_NAME = os.environ.get("WEBHOOK_HEADER", "X-Webhook-Token")
WEBHOOK_TOKEN_KEY = os.environ.get("WEBHOOK_TOKEN_KEY", "TRANSCRIPTION_WEBHOOK_TOKEN")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "")

_secrets_cache: Dict[str, Any] | None = None


def _load_secrets() -> Dict[str, Any]:
    global _secrets_cache
    if _secrets_cache is not None:
        return _secrets_cache
    if not CONFIG_SECRET_ARN:
        raise RuntimeError("CONFIG_SECRET_ARN environment variable not configured")
    client = boto3.client("secretsmanager", region_name=AWS_REGION)
    response = client.get_secret_value(SecretId=CONFIG_SECRET_ARN)
    secret_string = response.get("SecretString")
    if not secret_string:
        raise RuntimeError("SecretString missing in secret value")
    _secrets_cache = json.loads(secret_string)
    return _secrets_cache


def _api_request(path: str, payload: Dict[str, Any], method: str = "POST") -> Dict[str, Any]:
    if not API_BASE_URL:
        raise RuntimeError("API_BASE_URL environment variable not configured")
    url = f"{API_BASE_URL}{path}"
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    secrets = _load_secrets()
    token = secrets.get(WEBHOOK_TOKEN_KEY)
    if not token:
        raise RuntimeError("Webhook token missing from secret")
    headers[WEBHOOK_HEADER_NAME] = token
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data) if data else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8") if exc.fp else exc.reason
        raise RuntimeError(f"API request failed: {exc.code} {detail}") from exc


def _media_format_from_key(key: str) -> str | None:
    lowered = key.lower()
    for ext in (".mp3", ".mp4", ".wav", ".flac", ".m4a", ".ogg", ".amr"):
        if lowered.endswith(ext):
            return ext.replace(".", "")
    return None


def _start_transcription_job(key: str, job_name: str, media_format: str | None) -> None:
    secrets = _load_secrets()
    transcribe_role = secrets.get("TRANSCRIBE_ROLE_ARN")
    if not transcribe_role:
        raise RuntimeError("TRANSCRIBE_ROLE_ARN not configured in secret")

    kms_key = secrets.get("S3_KMS_KEY_ARN")
    language_code = secrets.get("TRANSCRIBE_LANGUAGE_CODE", "es-US")

    client = boto3.client("transcribe", region_name=AWS_REGION)
    media_uri = f"s3://{BUCKET_NAME}/{key}"
    raw_prefix = secrets.get("TRANSCRIPTS_PREFIX", RAW_TRANSCRIPTS_PREFIX)
    output_key = f"{raw_prefix}{job_name}/"

    kwargs: Dict[str, Any] = {
        "TranscriptionJobName": job_name,
        "Media": {"MediaFileUri": media_uri},
        "OutputBucketName": BUCKET_NAME,
        "OutputKey": output_key,
        "DataAccessRoleArn": transcribe_role,
    }
    if media_format:
        kwargs["MediaFormat"] = media_format
    if kms_key:
        kwargs["OutputEncryptionKMSKeyId"] = kms_key
    if language_code:
        kwargs["LanguageCode"] = language_code

    client.start_transcription_job(**kwargs)


def _extract_id_and_job_name(record: Dict[str, Any]) -> Tuple[int, str]:
    key = record["s3"]["object"]["key"]
    create_payload = {"recording_key": key, "status": "transcribing"}
    response = _api_request("/api/transcriptions", create_payload, method="POST")
    record_id = response.get("id")
    if record_id is None:
        raise RuntimeError("Transcription API response missing id")
    job_name = f"transcription-{record_id}-{uuid.uuid4().hex[:8]}"
    update_payload = {"transcription_job_name": job_name}
    _api_request(f"/api/transcriptions/{record_id}", update_payload, method="PATCH")
    return record_id, job_name


def lambda_handler(event, _context):
    if "Records" not in event:
        raise ValueError("No S3 records in event")
    results = []
    for record in event["Records"]:
        key = record.get("s3", {}).get("object", {}).get("key")
        if not key:
            continue
        if not key.startswith("recordings/"):
            continue
        try:
            record_id, job_name = _extract_id_and_job_name(record)
            media_format = _media_format_from_key(key)
            _start_transcription_job(key, job_name, media_format)
            results.append({"key": key, "record_id": record_id, "job_name": job_name})
        except Exception as exc:  # pragma: no cover - defensive logging
            error_payload = {
                "status": "error",
                "error_message": str(exc),
            }
            try:
                response = _api_request(
                    "/api/transcriptions",
                    {"recording_key": key, "status": "error"},
                    method="POST",
                )
                if response.get("id"):
                    _api_request(
                        f"/api/transcriptions/{response['id']}",
                        error_payload,
                        method="PATCH",
                    )
            except Exception:
                pass
            results.append({"key": key, "error": str(exc)})
    return {"processed": results}

