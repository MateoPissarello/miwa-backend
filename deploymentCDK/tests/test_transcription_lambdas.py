import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

dispatcher = importlib.import_module("deploymentCDK.lambda.transcription_dispatcher")
completer = importlib.import_module("deploymentCDK.lambda.transcription_completer")


@pytest.fixture(autouse=True)
def reset_caches():
    dispatcher._secrets_cache = None
    completer._secret_cache = None
    yield
    dispatcher._secrets_cache = None
    completer._secret_cache = None


def test_dispatcher_creates_transcription_job(monkeypatch):
    dispatcher.CONFIG_SECRET_ARN = "arn:secret"
    dispatcher.API_BASE_URL = "https://api.example.com"
    dispatcher.BUCKET_NAME = "files-bucket"
    dispatcher._secrets_cache = {
        "TRANSCRIPTION_WEBHOOK_TOKEN": "token",
        "TRANSCRIBE_ROLE_ARN": "arn:role",
        "TRANSCRIPTS_PREFIX": "transcripts/raw/",
    }

    api_calls = []

    def fake_api_request(path, payload, method="POST"):
        api_calls.append((path, payload, method))
        if path == "/api/transcriptions" and method == "POST":
            return {"id": 123}
        return {"id": 123}

    monkeypatch.setattr(dispatcher, "_api_request", fake_api_request)

    started = []

    def fake_start(key, job_name, media_format):
        started.append((key, job_name, media_format))

    monkeypatch.setattr(dispatcher, "_start_transcription_job", fake_start)

    event = {
        "Records": [
            {"s3": {"object": {"key": "recordings/meeting.wav"}}},
            {"s3": {"object": {"key": "other/path.txt"}}},
        ]
    }

    result = dispatcher.lambda_handler(event, None)

    assert len(started) == 1
    key, job_name, media_format = started[0]
    assert key == "recordings/meeting.wav"
    assert job_name.startswith("transcription-123-")
    assert media_format == "wav"
    assert any(call[0] == "/api/transcriptions" and call[2] == "POST" for call in api_calls)
    assert result["processed"][0]["record_id"] == 123


def test_completer_generates_summary(monkeypatch):
    completer.CONFIG_SECRET_ARN = "arn:secret"
    completer.API_BASE_URL = "https://api.example.com"
    completer.BUCKET_NAME = "files-bucket"
    completer._secret_cache = {
        "TRANSCRIPTS_PREFIX": "transcripts/raw/",
        "TRANSCRIPTS_TEXT_PREFIX": "transcripts/text/",
        "SUMMARIES_PREFIX": "summaries/",
        "LLM_MODEL_ID": "model",
        "SUMMARY_PROMPT_TEMPLATE": "Summarize: {transcript}",
    }

    uploads = []

    class DummyStorage:
        def __init__(self, **_kwargs):
            pass

        def download_text(self, *, key: str, encoding: str = "utf-8"):
            return json.dumps({"results": {"transcripts": [{"transcript": "Hola"}]}})

        def upload_bytes(self, *, data: bytes, key: str, content_type: str, cache_control=None, metadata=None):
            uploads.append((key, data.decode("utf-8"), content_type))
            return f"https://example.com/{key}"

    monkeypatch.setattr(completer, "S3Storage", DummyStorage)
    monkeypatch.setattr(completer, "_invoke_llm", lambda template, transcript, model_id: {"summary": "Hola"})

    api_payloads = []

    def fake_call_api(path, payload, method="PATCH"):
        api_payloads.append((path, payload, method))
        return {"id": 123}

    monkeypatch.setattr(completer, "_call_api", fake_call_api)

    event = {
        "detail": {
            "TranscriptionJobName": "transcription-123-abcd",
            "TranscriptionJobStatus": "COMPLETED",
        }
    }

    result = completer.lambda_handler(event, None)

    assert result["status"] == "summarized"
    assert len(uploads) == 2
    assert any(key.endswith(".txt") for key, _, _ in uploads)
    assert any(key.endswith(".json") for key, _, _ in uploads)
    assert api_payloads[0][0] == "/api/transcriptions/123"
    assert api_payloads[0][1]["status"] == "summarized"
