"""blueprint lineage v1 (root/depth/fork_count/source_replay_id)

Revision ID: 0021_blueprint_lineage_v1
Revises: 0020_alerts_sent
Create Date: 2026-01-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_blueprint_lineage_v1"
down_revision = "0020_alerts_sent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "blueprints", sa.Column("fork_root_blueprint_id", sa.String(), nullable=True)
    )
    op.add_column(
        "blueprints",
        sa.Column("fork_depth", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "blueprints",
        sa.Column("fork_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "blueprints", sa.Column("source_replay_id", sa.String(), nullable=True)
    )

    op.create_index(
        "ix_blueprints_forked_from_id",
        "blueprints",
        ["forked_from_id"],
        unique=False,
    )
    op.create_index(
        "ix_blueprints_fork_root_blueprint_id",
        "blueprints",
        ["fork_root_blueprint_id"],
        unique=False,
    )
    op.create_index(
        "ix_blueprints_source_replay_id",
        "blueprints",
        ["source_replay_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_blueprints_source_replay_id", table_name="blueprints")
    op.drop_index("ix_blueprints_fork_root_blueprint_id", table_name="blueprints")
    op.drop_index("ix_blueprints_forked_from_id", table_name="blueprints")

    op.drop_column("blueprints", "source_replay_id")
    op.drop_column("blueprints", "fork_count")
    op.drop_column("blueprints", "fork_depth")
    op.drop_column("blueprints", "fork_root_blueprint_id")

