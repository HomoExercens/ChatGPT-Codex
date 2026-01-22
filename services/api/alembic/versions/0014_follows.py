"""follows (social)

Revision ID: 0014_follows
Revises: 0013_discord_oauth
Create Date: 2026-01-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_follows"
down_revision = "0013_discord_oauth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "follows",
        sa.Column(
            "follower_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "followee_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_follows_follower_user_id", "follows", ["follower_user_id"], unique=False)
    op.create_index("ix_follows_followee_user_id", "follows", ["followee_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_follows_followee_user_id", table_name="follows")
    op.drop_index("ix_follows_follower_user_id", table_name="follows")
    op.drop_table("follows")

