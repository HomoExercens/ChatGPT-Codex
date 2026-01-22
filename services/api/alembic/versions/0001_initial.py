"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-01-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("username", sa.String(), unique=True, nullable=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column(
            "is_guest", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "wallets",
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tokens_balance", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "blueprints",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("ruleset_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("spec_json", sa.Text(), nullable=False),
        sa.Column("spec_hash", sa.String(), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "training_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("ruleset_version", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("plan", sa.String(), nullable=False),
        sa.Column("budget_tokens", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ray_job_id", sa.String(), nullable=True),
    )

    op.create_table(
        "checkpoints",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "training_run_id",
            sa.String(),
            sa.ForeignKey("training_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("artifact_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "matches",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("ruleset_version", sa.String(), nullable=False),
        sa.Column("seed_set_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "user_a_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "user_b_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "blueprint_a_id",
            sa.String(),
            sa.ForeignKey("blueprints.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "blueprint_b_id",
            sa.String(),
            sa.ForeignKey("blueprints.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("result", sa.String(), nullable=False),
        sa.Column("elo_delta_a", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("elo_delta_b", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "replays",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "match_id",
            sa.String(),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("artifact_path", sa.String(), nullable=False),
        sa.Column("digest", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "ratings",
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("mode", sa.String(), primary_key=True),
        sa.Column("elo", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("games_played", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("ratings")
    op.drop_table("replays")
    op.drop_table("matches")
    op.drop_table("checkpoints")
    op.drop_table("training_runs")
    op.drop_table("blueprints")
    op.drop_table("wallets")
    op.drop_table("users")
