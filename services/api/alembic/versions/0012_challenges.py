"""challenges tables

Revision ID: 0012_challenges
Revises: 0011_metrics_and_experiments
Create Date: 2026-01-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_challenges"
down_revision = "0011_metrics_and_experiments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "challenges",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column(
            "target_blueprint_id",
            sa.String(),
            sa.ForeignKey("blueprints.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "target_replay_id",
            sa.String(),
            sa.ForeignKey("replays.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("start_sec", sa.Float(), nullable=True),
        sa.Column("end_sec", sa.Float(), nullable=True),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("ruleset_version", sa.String(), nullable=False),
        sa.Column("week_id", sa.String(), nullable=True),
        sa.Column("portal_id", sa.String(), nullable=True),
        sa.Column("augments_a_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("augments_b_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "creator_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_challenges_target_blueprint_id",
        "challenges",
        ["target_blueprint_id"],
        unique=False,
    )
    op.create_index(
        "ix_challenges_target_replay_id",
        "challenges",
        ["target_replay_id"],
        unique=False,
    )
    op.create_index("ix_challenges_week_id", "challenges", ["week_id"], unique=False)
    op.create_index(
        "ix_challenges_creator_user_id",
        "challenges",
        ["creator_user_id"],
        unique=False,
    )
    op.create_index("ix_challenges_status", "challenges", ["status"], unique=False)

    op.create_table(
        "challenge_attempts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "challenge_id",
            sa.String(),
            sa.ForeignKey("challenges.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "challenger_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_index", sa.Integer(), nullable=False),
        sa.Column(
            "match_id",
            sa.String(),
            sa.ForeignKey("matches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("result", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "challenge_id",
            "challenger_user_id",
            "attempt_index",
            name="uq_challenge_attempts_challenger_index",
        ),
    )
    op.create_index(
        "ix_challenge_attempts_challenge_id",
        "challenge_attempts",
        ["challenge_id"],
        unique=False,
    )
    op.create_index(
        "ix_challenge_attempts_challenger_user_id",
        "challenge_attempts",
        ["challenger_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_challenge_attempts_match_id",
        "challenge_attempts",
        ["match_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_challenge_attempts_match_id", table_name="challenge_attempts")
    op.drop_index(
        "ix_challenge_attempts_challenger_user_id", table_name="challenge_attempts"
    )
    op.drop_index("ix_challenge_attempts_challenge_id", table_name="challenge_attempts")
    op.drop_table("challenge_attempts")

    op.drop_index("ix_challenges_status", table_name="challenges")
    op.drop_index("ix_challenges_creator_user_id", table_name="challenges")
    op.drop_index("ix_challenges_week_id", table_name="challenges")
    op.drop_index("ix_challenges_target_replay_id", table_name="challenges")
    op.drop_index("ix_challenges_target_blueprint_id", table_name="challenges")
    op.drop_table("challenges")

