"""streak softening (freeze tokens)

Revision ID: 0024_user_progress_streak_freeze_v2
Revises: 0023_user_progress_v1
Create Date: 2026-01-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_user_progress_streak_freeze_v2"
down_revision = "0023_user_progress_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_progress",
        sa.Column("streak_freeze_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "user_progress",
        sa.Column("streak_freeze_awarded_week", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_user_progress_streak_freeze_awarded_week",
        "user_progress",
        ["streak_freeze_awarded_week"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_progress_streak_freeze_awarded_week",
        table_name="user_progress",
    )
    op.drop_column("user_progress", "streak_freeze_awarded_week")
    op.drop_column("user_progress", "streak_freeze_tokens")

