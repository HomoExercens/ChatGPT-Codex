"""alerts_sent table

Revision ID: 0020_alerts_sent
Revises: 0019_http_error_events
Create Date: 2026-01-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0020_alerts_sent"
down_revision = "0019_http_error_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alerts_sent",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("alert_key", sa.String(), nullable=False),
        sa.Column(
            "outbox_id",
            sa.String(),
            sa.ForeignKey("discord_outbox.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alerts_sent_alert_key", "alerts_sent", ["alert_key"])
    op.create_index("ix_alerts_sent_outbox_id", "alerts_sent", ["outbox_id"])
    op.create_index("ix_alerts_sent_created_at", "alerts_sent", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_alerts_sent_created_at", table_name="alerts_sent")
    op.drop_index("ix_alerts_sent_outbox_id", table_name="alerts_sent")
    op.drop_index("ix_alerts_sent_alert_key", table_name="alerts_sent")
    op.drop_table("alerts_sent")

