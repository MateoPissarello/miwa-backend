from sqlalchemy import Column, Integer, String, Enum, DateTime, Text
from datetime import datetime
import enum
from database import Base


class UserRole(enum.Enum):
    client = "client"
    admin = "admin"


class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, unique=True, nullable=False)
    last_name = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(Enum(UserRole, name="user_role"), default=UserRole.client)
    last_login = Column(DateTime, nullable=True, default=datetime.now)


class TranscriptionStatus(enum.Enum):
    uploaded = "uploaded"
    transcribing = "transcribing"
    summarized = "summarized"
    error = "error"


class TranscriptionRecord(Base):
    __tablename__ = "transcriptions"

    id = Column(Integer, primary_key=True, index=True)
    recording_key = Column(String, nullable=False, index=True)
    transcript_key = Column(String, nullable=True)
    summary_key = Column(String, nullable=True)
    transcript_text = Column(Text, nullable=True)
    summary_text = Column(Text, nullable=True)
    transcription_job_name = Column(String, nullable=True, unique=True)
    status = Column(
        Enum(TranscriptionStatus, name="transcription_status"),
        nullable=False,
        default=TranscriptionStatus.uploaded,
    )
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        onupdate=datetime.utcnow,
    )
