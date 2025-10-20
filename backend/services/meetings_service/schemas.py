"""Shared data structures for meeting artefacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Dict, Optional


class MeetingArtifactStatus(str, Enum):
    UPLOADED = "UPLOADED"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSCRIBED = "TRANSCRIBED"
    SUMMARIZING = "SUMMARIZING"
    SUMMARIZED = "SUMMARIZED"
    FAILED = "FAILED"

    @property
    def is_processing(self) -> bool:
        return self in {
            MeetingArtifactStatus.UPLOADED,
            MeetingArtifactStatus.TRANSCRIBING,
            MeetingArtifactStatus.SUMMARIZING,
        }


@dataclass(frozen=True)
class MeetingIdentifier:
    user_email: str
    meeting_name: str
    meeting_date: str
    basename: str

    def compose_pk(self) -> str:
        return f"{self.user_email}#{self.meeting_name}#{self.meeting_date}#{self.basename}"


@dataclass
class MeetingArtifact:
    identifier: MeetingIdentifier
    ext: str
    status: MeetingArtifactStatus
    s3_key_recording: str
    s3_key_transcription: Optional[str] = None
    s3_key_summary: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    duration_sec: Optional[float] = None
    language: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_ddb(cls, item: Dict[str, Any]) -> "MeetingArtifact":
        identifier = MeetingIdentifier(
            user_email=item.get("user_email", ""),
            meeting_name=item.get("meeting_name", ""),
            meeting_date=item.get("meeting_date", ""),
            basename=item.get("basename", ""),
        )
        status = MeetingArtifactStatus(item.get("status", MeetingArtifactStatus.UPLOADED.value))
        duration_val = item.get("duration_sec")
        if isinstance(duration_val, (int, float)):
            duration = float(duration_val)
        elif duration_val is not None:
            duration = float(duration_val)
        else:
            duration = None
        return cls(
            identifier=identifier,
            ext=item.get("ext", ""),
            status=status,
            s3_key_recording=item.get("s3_key_recording", ""),
            s3_key_transcription=item.get("s3_key_transcription"),
            s3_key_summary=item.get("s3_key_summary"),
            error_code=item.get("error_code"),
            error_message=item.get("error_message"),
            duration_sec=duration,
            language=item.get("language"),
            updated_at=item.get("updated_at"),
        )

    def to_ddb_item(self) -> Dict[str, Any]:  # pragma: no cover - helper for tests
        item: Dict[str, Any] = {
            "pk": self.identifier.compose_pk(),
            "user_email": self.identifier.user_email,
            "meeting_name": self.identifier.meeting_name,
            "meeting_date": self.identifier.meeting_date,
            "basename": self.identifier.basename,
            "ext": self.ext,
            "status": self.status.value,
            "s3_key_recording": self.s3_key_recording,
        }
        if self.s3_key_transcription:
            item["s3_key_transcription"] = self.s3_key_transcription
        if self.s3_key_summary:
            item["s3_key_summary"] = self.s3_key_summary
        if self.error_code:
            item["error_code"] = self.error_code
        if self.error_message:
            item["error_message"] = self.error_message
        if self.duration_sec is not None:
            item["duration_sec"] = self.duration_sec
        if self.language:
            item["language"] = self.language
        if self.updated_at:
            item["updated_at"] = self.updated_at
        return item


class SummaryPayloadValidationError(ValueError):
    """Raised when the LLM response does not match the expected schema."""


def validate_summary_payload(payload: Dict[str, Any]) -> None:
    """Ensure the JSON payload returned by the LLM respects the contract."""

    required_keys = {
        "titulo": str,
        "temas_tratados": list,
        "resumen_general": str,
        "pendientes": list,
        "tags": list,
        "acuerdos": list,
        "riesgos": list,
        "decisiones": list,
    }
    for key, expected_type in required_keys.items():
        if key not in payload:
            raise SummaryPayloadValidationError(f"Missing key '{key}' in summary payload")
        if not isinstance(payload[key], expected_type):
            raise SummaryPayloadValidationError(f"Field '{key}' must be of type {expected_type.__name__}")
    if len(payload["titulo"]) > 120:
        raise SummaryPayloadValidationError("Field 'titulo' exceeds 120 characters")
    for field in ("temas_tratados", "tags"):
        if not payload[field]:
            raise SummaryPayloadValidationError(f"Field '{field}' must contain at least one item")

