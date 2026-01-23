"""reactions + notifications (remix v3)

Revision ID: 0022_reactions_and_notifications_v3
Revises: 0021_blueprint_lineage_v1
Create Date: 2026-01-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_reactions_and_notifications_v3"
down_revision = "0021_blueprint_lineage_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "replay_reactions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("replay_id", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("reaction_type", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["replay_id"], ["replays.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "replay_id",
            "actor_id",
            "reaction_type",
            name="uq_replay_reactions_replay_actor_type",
        ),
    )
    op.create_index(
        "ix_replay_reactions_replay_id",
        "replay_reactions",
        ["replay_id"],
        unique=False,
    )
    op.create_index(
        "ix_replay_reactions_actor_id",
        "replay_reactions",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        "ix_replay_reactions_user_id",
        "replay_reactions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_replay_reactions_reaction_type",
        "replay_reactions",
        ["reaction_type"],
        unique=False,
    )
    op.create_index(
        "ix_replay_reactions_created_at",
        "replay_reactions",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("body", sa.String(), nullable=True),
        sa.Column("href", sa.String(), nullable=True),
        sa.Column("dedupe_key", sa.String(), nullable=True),
        sa.Column("meta_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "dedupe_key", name="uq_notifications_user_dedupe"
        ),
    )
    op.create_index(
        "ix_notifications_user_id", "notifications", ["user_id"], unique=False
    )
    op.create_index("ix_notifications_type", "notifications", ["type"], unique=False)
    op.create_index(
        "ix_notifications_dedupe_key", "notifications", ["dedupe_key"], unique=False
    )
    op.create_index(
        "ix_notifications_created_at",
        "notifications",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_read_at", "notifications", ["read_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_read_at", table_name="notifications")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_dedupe_key", table_name="notifications")
    op.drop_index("ix_notifications_type", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("ix_replay_reactions_created_at", table_name="replay_reactions")
    op.drop_index("ix_replay_reactions_reaction_type", table_name="replay_reactions")
    op.drop_index("ix_replay_reactions_user_id", table_name="replay_reactions")
    op.drop_index("ix_replay_reactions_actor_id", table_name="replay_reactions")
    op.drop_index("ix_replay_reactions_replay_id", table_name="replay_reactions")
    op.drop_table("replay_reactions")

