"""match modifiers (portal/augments)

Revision ID: 0005_match_modifiers
Revises: 0004_render_jobs
Create Date: 2026-01-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_match_modifiers"
down_revision = "0004_render_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("portal_id", sa.String(), nullable=True))
    op.add_column(
        "matches",
        sa.Column("augments_a_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "matches",
        sa.Column("augments_b_json", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("matches", "augments_b_json")
    op.drop_column("matches", "augments_a_json")
    op.drop_column("matches", "portal_id")

