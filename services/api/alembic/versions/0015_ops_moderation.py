"""ops moderation: report status, global hides, soft bans

Revision ID: 0015_ops_moderation
Revises: 0014_follows
Create Date: 2026-01-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_ops_moderation"
down_revision = "0014_follows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("reports") as batch:
        batch.add_column(sa.Column("status", sa.String(), nullable=False, server_default="open"))
        batch.add_column(sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_reports_status", "reports", ["status"], unique=False)

    op.create_table(
        "moderation_hides",
        sa.Column("target_type", sa.String(), primary_key=True),
        sa.Column("target_id", sa.String(), primary_key=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_moderation_hides_target_type",
        "moderation_hides",
        ["target_type"],
        unique=False,
    )
    op.create_index(
        "ix_moderation_hides_target_id",
        "moderation_hides",
        ["target_id"],
        unique=False,
    )

    op.create_table(
        "user_soft_bans",
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("banned_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_user_soft_bans_banned_until",
        "user_soft_bans",
        ["banned_until"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_soft_bans_banned_until", table_name="user_soft_bans")
    op.drop_table("user_soft_bans")

    op.drop_index("ix_moderation_hides_target_id", table_name="moderation_hides")
    op.drop_index("ix_moderation_hides_target_type", table_name="moderation_hides")
    op.drop_table("moderation_hides")

    op.drop_index("ix_reports_status", table_name="reports")
    with op.batch_alter_table("reports") as batch:
        batch.drop_column("resolved_at")
        batch.drop_column("status")

