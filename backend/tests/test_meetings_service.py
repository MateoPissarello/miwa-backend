"""Unit tests covering meeting helper utilities."""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.meetings_service.paths import MeetingS3Paths
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

