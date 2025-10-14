"""Add table to persist transcription processing state."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7a2a6bf2f4c5"
down_revision: Union[str, Sequence[str], None] = "48d0a76e6ed1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transcriptions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("recording_key", sa.String(), nullable=False),
        sa.Column("transcript_key", sa.String(), nullable=True),
        sa.Column("summary_key", sa.String(), nullable=True),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("transcription_job_name", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "uploaded",
                "transcribing",
                "summarized",
                "error",
                name="transcription_status",
            ),
            nullable=False,
            server_default="uploaded",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        op.f("ix_transcriptions_id"), "transcriptions", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_transcriptions_recording_key"),
        "transcriptions",
        ["recording_key"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_transcriptions_job_name",
        "transcriptions",
        ["transcription_job_name"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_transcriptions_job_name", "transcriptions", type_="unique")
    op.drop_index(op.f("ix_transcriptions_recording_key"), table_name="transcriptions")
    op.drop_index(op.f("ix_transcriptions_id"), table_name="transcriptions")
    op.drop_table("transcriptions")

