from __future__ import annotations

import base64
from typing import Tuple

TRANSCRIPTION_FOLDER = "transcripciones"
DEFAULT_STATUS = "INICIANDO_TRANSCRIPCION"
STATUS_IN_PROGRESS = "EN_PROCESO"
STATUS_COMPLETED = "TRANSCRIPCION_COMPLETADA"
STATUS_ERROR = "ERROR"


def encode_recording_id(s3_key: str) -> str:
    """Encode an S3 object key into a URL-safe opaque identifier."""

    encoded = base64.urlsafe_b64encode(s3_key.encode("utf-8")).decode("utf-8")
    return encoded.rstrip("=")


def decode_recording_id(recording_id: str) -> str:
    padding = "=" * (-len(recording_id) % 4)
    raw = recording_id + padding
    return base64.urlsafe_b64decode(raw.encode("utf-8")).decode("utf-8")


def extract_email_and_filename(key: str) -> Tuple[str, str]:
    """Return (email, filename) from a key shaped like uploads/<email>/<file>."""

    parts = key.split("/")
    if len(parts) < 3:
        raise ValueError("Recording key is not in the expected uploads/<email>/<file> format")
    return parts[1], parts[-1]


def build_transcription_key(email: str, filename: str) -> str:
    return f"{TRANSCRIPTION_FOLDER}/{email}/{filename}.txt"
