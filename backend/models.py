from sqlalchemy import Column, Integer, String, Enum, DateTime, ForeignKey, UniqueConstraint
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


class MeetingTranscript(Base):
    __tablename__ = "meeting_transcripts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    calendar_event_id = Column(String, nullable=False)
    calendar_summary = Column(String, nullable=True)
    started_at = Column(DateTime, nullable=True)
    recording_key = Column(String, nullable=True)
    transcript_key = Column(String, nullable=True)
    summary_key = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "calendar_event_id", name="uq_meeting_transcripts_user_event"),
    )
