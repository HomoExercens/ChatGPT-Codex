"""reports and hidden clips tables

Revision ID: 0010_reports_and_hidden_clips
Revises: 0009_referrals
Create Date: 2026-01-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_reports_and_hidden_clips"
down_revision = "0009_referrals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_hidden_clips",
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "replay_id",
            sa.String(),
            sa.ForeignKey("replays.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_user_hidden_clips_replay_id",
        "user_hidden_clips",
        ["replay_id"],
        unique=False,
    )

    op.create_table(
        "reports",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "reporter_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_reports_reporter_user_id", "reports", ["reporter_user_id"], unique=False
    )
    op.create_index("ix_reports_target_type", "reports", ["target_type"], unique=False)
    op.create_index("ix_reports_target_id", "reports", ["target_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_reports_target_id", table_name="reports")
    op.drop_index("ix_reports_target_type", table_name="reports")
    op.drop_index("ix_reports_reporter_user_id", table_name="reports")
    op.drop_table("reports")

    op.drop_index("ix_user_hidden_clips_replay_id", table_name="user_hidden_clips")
    op.drop_table("user_hidden_clips")

