"""clip likes table

Revision ID: 0008_clip_likes
Revises: 0007_match_queue_type_cosmetics
Create Date: 2026-01-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_clip_likes"
down_revision = "0007_match_queue_type_cosmetics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clip_likes",
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
        "ix_clip_likes_replay_id", "clip_likes", ["replay_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_clip_likes_replay_id", table_name="clip_likes")
    op.drop_table("clip_likes")

