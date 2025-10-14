"""Add meeting transcripts table

Revision ID: 1e5a72305c20
Revises: 48d0a76e6ed1
Create Date: 2025-03-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1e5a72305c20"
down_revision: Union[str, Sequence[str], None] = "48d0a76e6ed1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meeting_transcripts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("calendar_event_id", sa.String(), nullable=False),
        sa.Column("calendar_summary", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("recording_key", sa.String(), nullable=True),
        sa.Column("transcript_key", sa.String(), nullable=True),
        sa.Column("summary_key", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "calendar_event_id", name="uq_meeting_transcripts_user_event"),
    )
    op.create_index("ix_meeting_transcripts_user_id", "meeting_transcripts", ["user_id"], unique=False)
    op.create_index("ix_meeting_transcripts_status", "meeting_transcripts", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_meeting_transcripts_status", table_name="meeting_transcripts")
    op.drop_index("ix_meeting_transcripts_user_id", table_name="meeting_transcripts")
    op.drop_table("meeting_transcripts")
