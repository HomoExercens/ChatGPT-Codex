"""user progress (xp/level/streak)

Revision ID: 0023_user_progress_v1
Revises: 0022_reactions_and_notifications_v3
Create Date: 2026-01-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_user_progress_v1"
down_revision = "0022_reactions_and_notifications_v3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_progress",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("xp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("streak_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_active_day", sa.Date(), nullable=True),
        sa.Column("quests_claimed_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("perfect_wins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("one_shot_wins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clutch_wins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        "ix_user_progress_updated_at", "user_progress", ["updated_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_user_progress_updated_at", table_name="user_progress")
    op.drop_table("user_progress")

