"""referrals table

Revision ID: 0009_referrals
Revises: 0008_clip_likes
Create Date: 2026-01-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_referrals"
down_revision = "0008_clip_likes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "referrals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "creator_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "new_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("invalid_reason", sa.String(), nullable=True),
        sa.Column("device_id", sa.String(), nullable=True),
        sa.Column("ip_hash", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("credited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credited_match_id", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_referrals_creator_user_id", "referrals", ["creator_user_id"], unique=False
    )
    op.create_index("ix_referrals_new_user_id", "referrals", ["new_user_id"], unique=True)
    op.create_index("ix_referrals_device_id", "referrals", ["device_id"], unique=False)
    op.create_index("ix_referrals_ip_hash", "referrals", ["ip_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_referrals_ip_hash", table_name="referrals")
    op.drop_index("ix_referrals_device_id", table_name="referrals")
    op.drop_index("ix_referrals_new_user_id", table_name="referrals")
    op.drop_index("ix_referrals_creator_user_id", table_name="referrals")
    op.drop_table("referrals")

