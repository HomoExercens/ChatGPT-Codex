"""launch week engine v1: featured, quests, discord outbox

Revision ID: 0016_launch_week_engine_v1
Revises: 0015_ops_moderation
Create Date: 2026-01-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_launch_week_engine_v1"
down_revision = "0015_ops_moderation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "featured_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("title_override", sa.String(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
    )
    op.create_index("ix_featured_items_kind", "featured_items", ["kind"], unique=False)
    op.create_index(
        "ix_featured_items_target_id", "featured_items", ["target_id"], unique=False
    )
    op.create_index(
        "ix_featured_items_status", "featured_items", ["status"], unique=False
    )
    op.create_index(
        "ix_featured_items_priority", "featured_items", ["priority"], unique=False
    )
    op.create_index(
        "ix_featured_items_created_at", "featured_items", ["created_at"], unique=False
    )
    op.create_index(
        "ix_featured_items_starts_at", "featured_items", ["starts_at"], unique=False
    )
    op.create_index(
        "ix_featured_items_ends_at", "featured_items", ["ends_at"], unique=False
    )

    with op.batch_alter_table("wallets") as batch:
        batch.add_column(
            sa.Column("cosmetic_points", sa.Integer(), nullable=False, server_default="0")
        )

    op.create_table(
        "quests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("cadence", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("goal_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("filters_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("reward_cosmetic_id", sa.String(), nullable=False),
        sa.Column("reward_amount", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("cadence", "key", name="uq_quests_cadence_key"),
    )
    op.create_index("ix_quests_cadence", "quests", ["cadence"], unique=False)
    op.create_index("ix_quests_key", "quests", ["key"], unique=False)
    op.create_index("ix_quests_event_type", "quests", ["event_type"], unique=False)
    op.create_index("ix_quests_active_from", "quests", ["active_from"], unique=False)
    op.create_index("ix_quests_active_to", "quests", ["active_to"], unique=False)

    op.create_table(
        "quest_assignments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "quest_id",
            sa.String(),
            sa.ForeignKey("quests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_key", sa.String(), nullable=False),
        sa.Column("progress_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "quest_id",
            "user_id",
            "period_key",
            name="uq_quest_assignments_quest_user_period",
        ),
    )
    op.create_index(
        "ix_quest_assignments_user_id", "quest_assignments", ["user_id"], unique=False
    )
    op.create_index(
        "ix_quest_assignments_quest_id", "quest_assignments", ["quest_id"], unique=False
    )
    op.create_index(
        "ix_quest_assignments_period_key",
        "quest_assignments",
        ["period_key"],
        unique=False,
    )
    op.create_index(
        "ix_quest_assignments_claimed_at",
        "quest_assignments",
        ["claimed_at"],
        unique=False,
    )

    op.create_table(
        "quest_events_applied",
        sa.Column(
            "event_id",
            sa.String(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "assignment_id",
            sa.String(),
            sa.ForeignKey("quest_assignments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_quest_events_applied_assignment_id",
        "quest_events_applied",
        ["assignment_id"],
        unique=False,
    )

    op.create_table(
        "discord_outbox",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_discord_outbox_kind", "discord_outbox", ["kind"], unique=False)
    op.create_index(
        "ix_discord_outbox_status", "discord_outbox", ["status"], unique=False
    )
    op.create_index(
        "ix_discord_outbox_next_attempt_at",
        "discord_outbox",
        ["next_attempt_at"],
        unique=False,
    )
    op.create_index(
        "ix_discord_outbox_created_at",
        "discord_outbox",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_discord_outbox_created_at", table_name="discord_outbox")
    op.drop_index("ix_discord_outbox_next_attempt_at", table_name="discord_outbox")
    op.drop_index("ix_discord_outbox_status", table_name="discord_outbox")
    op.drop_index("ix_discord_outbox_kind", table_name="discord_outbox")
    op.drop_table("discord_outbox")

    op.drop_index(
        "ix_quest_events_applied_assignment_id", table_name="quest_events_applied"
    )
    op.drop_table("quest_events_applied")

    op.drop_index("ix_quest_assignments_claimed_at", table_name="quest_assignments")
    op.drop_index("ix_quest_assignments_period_key", table_name="quest_assignments")
    op.drop_index("ix_quest_assignments_quest_id", table_name="quest_assignments")
    op.drop_index("ix_quest_assignments_user_id", table_name="quest_assignments")
    op.drop_table("quest_assignments")

    op.drop_index("ix_quests_active_to", table_name="quests")
    op.drop_index("ix_quests_active_from", table_name="quests")
    op.drop_index("ix_quests_event_type", table_name="quests")
    op.drop_index("ix_quests_key", table_name="quests")
    op.drop_index("ix_quests_cadence", table_name="quests")
    op.drop_table("quests")

    with op.batch_alter_table("wallets") as batch:
        batch.drop_column("cosmetic_points")

    op.drop_index("ix_featured_items_ends_at", table_name="featured_items")
    op.drop_index("ix_featured_items_starts_at", table_name="featured_items")
    op.drop_index("ix_featured_items_created_at", table_name="featured_items")
    op.drop_index("ix_featured_items_priority", table_name="featured_items")
    op.drop_index("ix_featured_items_status", table_name="featured_items")
    op.drop_index("ix_featured_items_target_id", table_name="featured_items")
    op.drop_index("ix_featured_items_kind", table_name="featured_items")
    op.drop_table("featured_items")

