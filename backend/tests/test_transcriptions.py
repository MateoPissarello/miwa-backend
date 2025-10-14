"""Tests for the transcription service endpoints."""

from __future__ import annotations

import time
from datetime import datetime

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models import MeetingTranscript, User, UserRole
from services.s3_service.deps import get_s3_storage
from utils.get_current_user_cognito import TokenData, get_current_user


TEST_ENGINE = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


class FakeS3Storage:
    def presign_get_url(self, key: str, expires_seconds: int = 900) -> str:  # noqa: D401
        return f"https://s3.local/{key}?expires={expires_seconds}"


def _override_db() -> Session:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _override_user() -> TokenData:
    return TokenData(
        sub="user-123",
        username="user@example.com",
        email="user@example.com",
        token_use="access",
        exp=int(time.time()) + 3600,
        user_id=1,
    )


@pytest.fixture(autouse=True)
def _prepare_database():
    Base.metadata.drop_all(bind=TEST_ENGINE)
    Base.metadata.create_all(bind=TEST_ENGINE)
    with TestingSessionLocal() as db:
        db.add(
            User(
                user_id=1,
                first_name="Test",
                last_name="User",
                email="user@example.com",
                password="secret",
                role=UserRole.client,
            )
        )
        db.commit()
    yield


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_s3_storage] = lambda: FakeS3Storage()
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def test_create_transcription_inserts_record(client: TestClient):
    payload = {
        "calendar_event_id": "evt-1",
        "recording_key": "recordings/user/meeting.mp3",
        "calendar_summary": "Kick-off",
        "started_at": datetime.utcnow().isoformat(),
        "transcript_key": "transcripts/evt-1.json",
        "summary_key": "summaries/evt-1.txt",
    }

    response = client.post("/api/transcriptions", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["calendar_event_id"] == "evt-1"
    assert data["status"] == "uploaded"
    assert data["recording_url"].startswith("https://s3.local/recordings/")

    with TestingSessionLocal() as db:
        db_obj = db.query(MeetingTranscript).filter_by(calendar_event_id="evt-1").one()
        assert db_obj.status == "uploaded"
        assert db_obj.recording_key == payload["recording_key"]


def test_list_transcriptions_returns_presigned_urls(client: TestClient):
    payload = {
        "calendar_event_id": "evt-42",
        "recording_key": "recordings/user/event42.mp3",
        "calendar_summary": "Weekly sync",
        "summary_key": "summaries/evt-42.txt",
    }
    client.post("/api/transcriptions", json=payload)

    response = client.get("/api/transcriptions")
    assert response.status_code == 200
    data = response.json()
    assert data["items"], "Should return at least one item"
    item = data["items"][0]
    assert item["calendar_event_id"] == "evt-42"
    assert item["recording_url"].endswith("event42.mp3?expires=900")
    assert item["summary_url"].endswith("evt-42.txt?expires=900")


def test_summary_endpoint_returns_presigned_url(client: TestClient):
    payload = {
        "calendar_event_id": "evt-sum",
        "recording_key": "recordings/user/event.mp3",
        "summary_key": "summaries/evt-sum.txt",
    }
    create_resp = client.post("/api/transcriptions", json=payload)
    transcription_id = create_resp.json()["id"]

    response = client.get(f"/api/transcriptions/{transcription_id}/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["summary_url"].endswith("evt-sum.txt?expires=900")
