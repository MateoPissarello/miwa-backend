import os

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from main import app
from kernel.runtime import get_kernel
from services.transcription_service.deps import get_transcription_service
from services.transcription_service.service import TranscriptionService
from services.transcription_service.schemas import TranscriptionStatus


os.environ.setdefault("TRANSCRIBE_ROLE_ARN", "test-role")
os.environ.setdefault("TRANSCRIPTS_PREFIX", "transcripts/raw/")
os.environ.setdefault("SUMMARIES_PREFIX", "summaries/")
os.environ.setdefault("LLM_MODEL_ID", "test-model")
os.environ.setdefault("SUMMARY_PROMPT_TEMPLATE", "Summarize: {transcript}")
os.environ.setdefault("TRANSCRIPTION_WEBHOOK_TOKEN", "test-token")


class DummyStorage:
    def presign_get_url(self, key: str, expires_seconds: int = 3600) -> str:  # pragma: no cover - trivial
        return f"https://example.com/{key}"


@pytest.fixture(scope="module")
def client():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    storage = DummyStorage()
    kernel = get_kernel()
    service = TranscriptionService(
        session_factory=session_factory,
        settings=kernel.settings,
        storage=storage,  # type: ignore[arg-type]
    )

    app.dependency_overrides[get_transcription_service] = lambda: service
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.pop(get_transcription_service, None)


def test_create_transcription_record(client):
    response = client.post(
        "/api/transcriptions",
        json={"recording_key": "recordings/sample.wav", "status": "transcribing"},
        headers={"X-Webhook-Token": "test-token"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == TranscriptionStatus.transcribing
    assert body["recording_url"].startswith("https://example.com/")


def test_update_transcription_record(client):
    create = client.post(
        "/api/transcriptions",
        json={"recording_key": "recordings/sample.wav", "status": "transcribing"},
        headers={"X-Webhook-Token": "test-token"},
    ).json()
    record_id = create["id"]
    update = client.patch(
        f"/api/transcriptions/{record_id}",
        json={
            "status": "summarized",
            "transcript_key": "transcripts/text/sample.txt",
            "summary_key": "summaries/sample.json",
            "transcript_text": "Hola mundo",
            "summary_text": "{\"summary\": \"Hola\"}",
        },
        headers={"X-Webhook-Token": "test-token"},
    )
    assert update.status_code == 200
    payload = update.json()
    assert payload["status"] == TranscriptionStatus.summarized
    listing = client.get("/api/transcriptions")
    assert listing.status_code == 200
    items = listing.json()
    assert len(items) >= 1
    assert any(item["status"] == TranscriptionStatus.summarized for item in items)
