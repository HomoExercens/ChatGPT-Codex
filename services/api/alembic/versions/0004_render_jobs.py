"""render jobs table

Revision ID: 0004_render_jobs
Revises: 0003_blueprint_meta_submitted_at
Create Date: 2026-01-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_render_jobs"
down_revision = "0003_blueprint_meta_submitted_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "render_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column(
            "target_replay_id",
            sa.String(),
            sa.ForeignKey("replays.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "target_match_id",
            sa.String(),
            sa.ForeignKey("matches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("params_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("cache_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ray_job_id", sa.String(), nullable=True),
        sa.Column("artifact_path", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_render_jobs_user_id", "render_jobs", ["user_id"])
    op.create_index("ix_render_jobs_cache_key", "render_jobs", ["cache_key"])
    op.create_index("ix_render_jobs_target_replay_id", "render_jobs", ["target_replay_id"])
    op.create_index("ix_render_jobs_target_match_id", "render_jobs", ["target_match_id"])


def downgrade() -> None:
    op.drop_index("ix_render_jobs_target_match_id", table_name="render_jobs")
    op.drop_index("ix_render_jobs_target_replay_id", table_name="render_jobs")
    op.drop_index("ix_render_jobs_cache_key", table_name="render_jobs")
    op.drop_index("ix_render_jobs_user_id", table_name="render_jobs")
    op.drop_table("render_jobs")

