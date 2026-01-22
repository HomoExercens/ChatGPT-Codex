"""ugc: blueprint origin_code_hash for build code imports

Revision ID: 0017_build_code_origin_hash
Revises: 0016_launch_week_engine_v1
Create Date: 2026-01-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_build_code_origin_hash"
down_revision = "0016_launch_week_engine_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("blueprints") as batch:
        batch.add_column(sa.Column("origin_code_hash", sa.String(), nullable=True))
    op.create_index(
        "ix_blueprints_origin_code_hash",
        "blueprints",
        ["origin_code_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_blueprints_origin_code_hash", table_name="blueprints")
    with op.batch_alter_table("blueprints") as batch:
        batch.drop_column("origin_code_hash")
