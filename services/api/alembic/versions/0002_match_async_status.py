"""match async status fields

Revision ID: 0002_match_async_status
Revises: 0001_initial
Create Date: 2026-01-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_match_async_status"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("status", sa.String(), nullable=False, server_default="done"),
    )
    op.add_column(
        "matches",
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("matches", sa.Column("ray_job_id", sa.String(), nullable=True))
    op.add_column("matches", sa.Column("error_message", sa.Text(), nullable=True))

    # Existing rows are completed matches.
    op.execute("UPDATE matches SET progress=100 WHERE finished_at IS NOT NULL")


def downgrade() -> None:
    op.drop_column("matches", "error_message")
    op.drop_column("matches", "ray_job_id")
    op.drop_column("matches", "progress")
    op.drop_column("matches", "status")

