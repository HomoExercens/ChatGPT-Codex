"""perf: hot query indexes for public alpha

Revision ID: 0018_hot_query_indexes
Revises: 0017_build_code_origin_hash
Create Date: 2026-01-20
"""

from __future__ import annotations

from alembic import op

revision = "0018_hot_query_indexes"
down_revision = "0017_build_code_origin_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_events_created_at", "events", ["created_at"], unique=False)
    op.create_index(
        "ix_events_type_created_at", "events", ["type", "created_at"], unique=False
    )
    op.create_index(
        "ix_events_user_id_created_at", "events", ["user_id", "created_at"], unique=False
    )

    op.create_index(
        "ix_render_jobs_status_created_at",
        "render_jobs",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_render_jobs_cache_key_created_at",
        "render_jobs",
        ["cache_key", "created_at"],
        unique=False,
    )

    op.create_index(
        "ix_matches_user_a_id_mode_created_at",
        "matches",
        ["user_a_id", "mode", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_matches_queue_type_status_created_at",
        "matches",
        ["queue_type", "status", "created_at"],
        unique=False,
    )

    op.create_index(
        "ix_clip_likes_replay_id_created_at",
        "clip_likes",
        ["replay_id", "created_at"],
        unique=False,
    )

    op.create_index(
        "ix_reports_status_created_at",
        "reports",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_reports_status_created_at", table_name="reports")

    op.drop_index("ix_clip_likes_replay_id_created_at", table_name="clip_likes")

    op.drop_index("ix_matches_queue_type_status_created_at", table_name="matches")
    op.drop_index("ix_matches_user_a_id_mode_created_at", table_name="matches")

    op.drop_index("ix_render_jobs_cache_key_created_at", table_name="render_jobs")
    op.drop_index("ix_render_jobs_status_created_at", table_name="render_jobs")

    op.drop_index("ix_events_user_id_created_at", table_name="events")
    op.drop_index("ix_events_type_created_at", table_name="events")
    op.drop_index("ix_events_created_at", table_name="events")
