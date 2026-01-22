"""blueprint meta_json + submitted_at

Revision ID: 0003_blueprint_meta_submitted_at
Revises: 0002_match_async_status
Create Date: 2026-01-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_blueprint_meta_submitted_at"
down_revision = "0002_match_async_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "blueprints",
        sa.Column("meta_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "blueprints",
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Backfill: treat existing submitted blueprints as submitted at their last update.
    op.execute(
        "UPDATE blueprints SET submitted_at=updated_at "
        "WHERE status='submitted' AND submitted_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("blueprints", "submitted_at")
    op.drop_column("blueprints", "meta_json")

