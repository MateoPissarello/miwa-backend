"""Helpers to compute canonical S3 keys for meeting artefacts."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Tuple
from urllib.parse import unquote_plus

from .schemas import MeetingIdentifier


_KEY_PATTERN = re.compile(
    r"^grabaciones/(?P<user_email>[^/]+)/(?P<folder>[^/]+)/(?P<basename>[^/.]+)(?P<ext>\.[^.]+)$"
)


@dataclass(frozen=True)
class MeetingS3Paths:
    identifier: MeetingIdentifier
    ext: str

    @property
    def folder(self) -> str:
        return f"{self.identifier.meeting_name}_{self.identifier.meeting_date}"

    @property
    def recording_key(self) -> str:
        return f"grabaciones/{self.identifier.user_email}/{self.folder}/{self.identifier.basename}{self.ext}"

    @property
    def transcription_key(self) -> str:
        return f"transcripciones/{self.identifier.user_email}/{self.folder}/{self.identifier.basename}.json"

    @property
    def summary_key(self) -> str:
        return f"resumenes/{self.identifier.user_email}/{self.folder}/{self.identifier.basename}.json"

    @property
    def transcription_output_prefix(self) -> str:
        return f"transcripciones/raw/{self.identifier.user_email}/{self.folder}/"

    @classmethod
    def parse_from_recording_key(cls, key: str) -> "MeetingS3Paths":
        decoded = unquote_plus(key)
        match = _KEY_PATTERN.match(decoded)
        if not match:
            raise ValueError(f"Invalid recording key format: {key}")
        folder = match.group("folder")
        if "_" not in folder:
            raise ValueError(f"Folder must follow meeting_name_meeting_date pattern: {folder}")
        meeting_name, meeting_date = folder.split("_", 1)
        identifier = MeetingIdentifier(
            user_email=match.group("user_email"),
            meeting_name=meeting_name,
            meeting_date=meeting_date,
            basename=match.group("basename"),
        )
        return cls(identifier=identifier, ext=match.group("ext"))


def build_all_s3_keys(identifier: MeetingIdentifier, ext: str) -> Tuple[str, str, str]:
    paths = MeetingS3Paths(identifier=identifier, ext=ext)
    return paths.recording_key, paths.transcription_key, paths.summary_key


def split_filename(filename: str) -> Tuple[str, str]:
    """Split a filename into basename and extension enforcing security rules."""

    candidate = filename.strip()
    if not candidate:
        raise ValueError("Filename cannot be empty")
    if any(sep in candidate for sep in ("/", "\\")):
        raise ValueError("Filename must not contain path separators")
    if candidate.startswith("."):
        raise ValueError("Filename must not start with a dot")
    basename, ext = os.path.splitext(candidate)
    if not basename or not ext:
        raise ValueError("Filename must include a basename and extension")
    if basename in {".", ".."}:
        raise ValueError("Filename basename is invalid")
    return basename, ext


__all__ = ["MeetingS3Paths", "build_all_s3_keys", "split_filename"]

