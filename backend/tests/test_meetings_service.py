"""Unit tests covering meeting helper utilities."""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.meetings_service.handlers import _build_transcription_payload, _parse_s3_uri, _sanitize_job_name
from services.meetings_service.paths import MeetingS3Paths, split_filename
from services.meetings_service.schemas import (
    MeetingIdentifier,
    SummaryPayloadValidationError,
    validate_summary_payload,
)


def test_parse_recording_key_roundtrip():
    identifier = MeetingIdentifier(
        user_email="paquito@gmail.com",
        meeting_name="Daily",
        meeting_date="2025-10-25",
        basename="grabacion",
    )
    paths = MeetingS3Paths(identifier=identifier, ext=".mp4")
    parsed = MeetingS3Paths.parse_from_recording_key(paths.recording_key)
    assert parsed.identifier == identifier
    assert parsed.ext == ".mp4"


def test_split_filename_valid():
    basename, ext = split_filename("grabacion.MP4")
    assert basename == "grabacion"
    assert ext == ".MP4"


@pytest.mark.parametrize(
    "filename",
    ["", "../escape.mp3", "sin_ext", ".hidden", "video", ".."],
)
def test_split_filename_invalid(filename):
    with pytest.raises(ValueError):
        split_filename(filename)


def test_validate_summary_payload_success():
    payload = {
        "titulo": "Daily 2025-10-25 — Avances",
        "temas_tratados": ["Tema 1", "Tema 2"],
        "resumen_general": "Resumen.",
        "pendientes": [],
        "tags": ["daily", "backend", "s3"],
        "acuerdos": [],
        "riesgos": [],
        "decisiones": [],
    }
    validate_summary_payload(payload)


@pytest.mark.parametrize(
    "payload, error",
    [
        ({"temas_tratados": []}, "Missing key"),
        (
            {
                "titulo": "x" * 121,
                "temas_tratados": ["tema"],
                "resumen_general": "",
                "pendientes": [],
                "tags": ["tag"],
                "acuerdos": [],
                "riesgos": [],
                "decisiones": [],
            },
            "exceeds",
        ),
    ],
)
def test_validate_summary_payload_errors(payload, error):
    with pytest.raises(SummaryPayloadValidationError) as excinfo:
        validate_summary_payload(payload)
    assert error in str(excinfo.value)


def test_sanitize_job_name_limits_length():
    identifier = MeetingIdentifier(
        user_email="usuario.largo+demo@example.com",
        meeting_name="Sprint Review",
        meeting_date="2025-01-31",
        basename="demo",
    )
    paths = MeetingS3Paths(identifier=identifier, ext=".mp4")
    result = _sanitize_job_name(paths)
    assert "@" not in result
    assert len(result) <= 200


def test_parse_s3_uri_handles_virtual_host():
    bucket, key = _parse_s3_uri("https://mi-bucket.s3.amazonaws.com/transcripciones/job.json")
    assert bucket == "mi-bucket"
    assert key == "transcripciones/job.json"


def test_build_transcription_payload_creates_segment():
    raw = {
        "results": {
            "items": [
                {"type": "pronunciation", "start_time": "0.0", "end_time": "1.0", "alternatives": [{"content": "Hola"}]},
                {"type": "pronunciation", "start_time": "1.0", "end_time": "2.5", "alternatives": [{"content": "mundo"}]},
            ],
            "transcripts": [{"transcript": "Hola mundo"}],
        }
    }
    payload, duration = _build_transcription_payload(raw, language="es")
    assert payload["language"] == "es"
    assert payload["segments"][0]["text"] == "Hola mundo"
    assert duration == pytest.approx(2.5, rel=1e-6)

