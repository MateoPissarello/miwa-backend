"""Lambda handler that finalises transcription jobs and generates summaries."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict

import boto3

from .s3_storage import S3Storage


CONFIG_SECRET_ARN = os.environ.get("CONFIG_SECRET_ARN", "")
API_BASE_URL = os.environ.get("API_BASE_URL", "").rstrip("/")
RAW_TRANSCRIPTS_PREFIX = os.environ.get("RAW_TRANSCRIPTS_PREFIX", "transcripts/raw/")
TEXT_TRANSCRIPTS_PREFIX = os.environ.get("TEXT_TRANSCRIPTS_PREFIX", "transcripts/text/")
SUMMARIES_PREFIX = os.environ.get("SUMMARIES_PREFIX", "summaries/")
WEBHOOK_HEADER_NAME = os.environ.get("WEBHOOK_HEADER", "X-Webhook-Token")
WEBHOOK_TOKEN_KEY = os.environ.get("WEBHOOK_TOKEN_KEY", "TRANSCRIPTION_WEBHOOK_TOKEN")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "")

_secret_cache: Dict[str, Any] | None = None


def _load_secret() -> Dict[str, Any]:
    global _secret_cache
    if _secret_cache is not None:
        return _secret_cache
    if not CONFIG_SECRET_ARN:
        raise RuntimeError("CONFIG_SECRET_ARN environment variable not configured")
    client = boto3.client("secretsmanager", region_name=AWS_REGION)
    response = client.get_secret_value(SecretId=CONFIG_SECRET_ARN)
    secret_string = response.get("SecretString")
    if not secret_string:
        raise RuntimeError("SecretString missing in secret")
    _secret_cache = json.loads(secret_string)
    return _secret_cache


def _call_api(path: str, payload: Dict[str, Any], method: str = "PATCH") -> Dict[str, Any]:
    if not API_BASE_URL:
        raise RuntimeError("API_BASE_URL environment variable not configured")
    url = f"{API_BASE_URL}{path}"
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    secret = _load_secret()
    token = secret.get(WEBHOOK_TOKEN_KEY)
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


def _transcript_key(job_name: str, raw_prefix: str) -> str:
    return f"{raw_prefix}{job_name}/{job_name}.json"


def _text_transcript_key(job_name: str, text_prefix: str) -> str:
    return f"{text_prefix}{job_name}.txt"


def _summary_key(job_name: str, summary_prefix: str) -> str:
    return f"{summary_prefix}{job_name}.json"


def _extract_record_id(job_name: str) -> int:
    parts = job_name.split("-")
    if len(parts) < 3:
        raise RuntimeError("Unexpected job name format")
    try:
        return int(parts[1])
    except ValueError as exc:
        raise RuntimeError("Could not parse transcription id from job name") from exc


def _download_transcript(job_name: str, storage: S3Storage, raw_prefix: str) -> Dict[str, Any]:
    key = _transcript_key(job_name, raw_prefix)
    raw_json = storage.download_text(key=key)
    return json.loads(raw_json)


def _extract_text(transcript_payload: Dict[str, Any]) -> str:
    results = transcript_payload.get("results", {})
    transcripts = results.get("transcripts", [])
    if transcripts:
        return transcripts[0].get("transcript", "")
    return ""


def _invoke_llm(prompt_template: str, transcript_text: str, model_id: str) -> Dict[str, Any]:
    client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    prompt = prompt_template.format(transcript=transcript_text)
    body = json.dumps({"inputText": prompt})
    response = client.invoke_model(modelId=model_id, body=body)
    payload = response["body"].read().decode("utf-8") if hasattr(response["body"], "read") else response["body"]
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        data = {"summary": payload.strip()}
    return data


def lambda_handler(event, _context):
    detail = event.get("detail", {})
    job_name = detail.get("TranscriptionJobName")
    job_status = detail.get("TranscriptionJobStatus")
    if not job_name or job_status != "COMPLETED":
        return {"ignored": True}

    secret = _load_secret()
    kms_key = secret.get("S3_KMS_KEY_ARN")
    model_id = secret.get("LLM_MODEL_ID")
    prompt_template = secret.get("SUMMARY_PROMPT_TEMPLATE")
    if not model_id or not prompt_template:
        raise RuntimeError("LLM configuration missing in secret")

    storage = S3Storage(bucket=BUCKET_NAME, region=AWS_REGION, kms_key_id=kms_key)

    try:
        raw_prefix = secret.get("TRANSCRIPTS_PREFIX", RAW_TRANSCRIPTS_PREFIX)
        text_prefix = secret.get("TRANSCRIPTS_TEXT_PREFIX", TEXT_TRANSCRIPTS_PREFIX)
        summary_prefix = secret.get("SUMMARIES_PREFIX", SUMMARIES_PREFIX)
        transcript_payload = _download_transcript(job_name, storage, raw_prefix)
        transcript_text = _extract_text(transcript_payload)
        storage.upload_bytes(
            data=transcript_text.encode("utf-8"),
            key=_text_transcript_key(job_name, text_prefix),
            content_type="text/plain",
        )
        summary_payload = _invoke_llm(prompt_template, transcript_text, model_id)
        summary_bytes = json.dumps(summary_payload, ensure_ascii=False).encode("utf-8")
        storage.upload_bytes(
            data=summary_bytes,
            key=_summary_key(job_name, summary_prefix),
            content_type="application/json",
        )
        record_id = _extract_record_id(job_name)
        update_payload = {
            "status": "summarized",
            "transcript_key": _text_transcript_key(job_name, text_prefix),
            "summary_key": _summary_key(job_name, summary_prefix),
            "transcript_text": transcript_text,
            "summary_text": json.dumps(summary_payload, ensure_ascii=False),
        }
        _call_api(f"/api/transcriptions/{record_id}", update_payload)
        return {"record_id": record_id, "job_name": job_name, "status": "summarized"}
    except Exception as exc:
        record_id = None
        try:
            record_id = _extract_record_id(job_name)
            _call_api(
                f"/api/transcriptions/{record_id}",
                {"status": "error", "error_message": str(exc)},
            )
        except Exception:
            pass
        raise

