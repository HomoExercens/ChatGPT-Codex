"""blueprint UGC fields (forked_from_id, build_code)

Revision ID: 0006_blueprint_ugc_fields
Revises: 0005_match_modifiers
Create Date: 2026-01-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_blueprint_ugc_fields"
down_revision = "0005_match_modifiers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("blueprints", sa.Column("forked_from_id", sa.String(), nullable=True))
    op.add_column("blueprints", sa.Column("build_code", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("blueprints", "build_code")
    op.drop_column("blueprints", "forked_from_id")

