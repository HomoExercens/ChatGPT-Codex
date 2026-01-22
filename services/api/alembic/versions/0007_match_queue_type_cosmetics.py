"""match queue_type/week_id + cosmetics tables

Revision ID: 0007_match_queue_type_cosmetics
Revises: 0006_blueprint_ugc_fields
Create Date: 2026-01-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_match_queue_type_cosmetics"
down_revision = "0006_blueprint_ugc_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("queue_type", sa.String(), nullable=False, server_default="ranked"),
    )
    op.add_column("matches", sa.Column("week_id", sa.String(), nullable=True))
    op.create_index("ix_matches_queue_type", "matches", ["queue_type"], unique=False)
    op.create_index("ix_matches_week_id", "matches", ["week_id"], unique=False)

    op.create_table(
        "cosmetics",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("asset_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "user_cosmetics",
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "cosmetic_id",
            sa.String(),
            sa.ForeignKey("cosmetics.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("earned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_cosmetics")
    op.drop_table("cosmetics")
    op.drop_index("ix_matches_week_id", table_name="matches")
    op.drop_index("ix_matches_queue_type", table_name="matches")
    op.drop_column("matches", "week_id")
    op.drop_column("matches", "queue_type")

