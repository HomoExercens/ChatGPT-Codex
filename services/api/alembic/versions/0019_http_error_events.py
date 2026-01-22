"""http_error_events table

Revision ID: 0019_http_error_events
Revises: 0018_hot_query_indexes
Create Date: 2026-01-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0019_http_error_events"
down_revision = "0018_hot_query_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "http_error_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_http_error_events_created_at", "http_error_events", ["created_at"]
    )
    op.create_index("ix_http_error_events_path", "http_error_events", ["path"])
    op.create_index("ix_http_error_events_method", "http_error_events", ["method"])
    op.create_index("ix_http_error_events_status", "http_error_events", ["status"])
    op.create_index(
        "ix_http_error_events_request_id", "http_error_events", ["request_id"]
    )
    op.create_index(
        "ix_http_error_events_grouped",
        "http_error_events",
        ["path", "method", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_http_error_events_grouped", table_name="http_error_events")
    op.drop_index("ix_http_error_events_request_id", table_name="http_error_events")
    op.drop_index("ix_http_error_events_status", table_name="http_error_events")
    op.drop_index("ix_http_error_events_method", table_name="http_error_events")
    op.drop_index("ix_http_error_events_path", table_name="http_error_events")
    op.drop_index("ix_http_error_events_created_at", table_name="http_error_events")
    op.drop_table("http_error_events")

