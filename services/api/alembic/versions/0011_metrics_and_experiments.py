"""metrics and experiments tables

Revision ID: 0011_metrics_and_experiments
Revises: 0010_reports_and_hidden_clips
Create Date: 2026-01-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_metrics_and_experiments"
down_revision = "0010_reports_and_hidden_clips"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("variants_json", sa.Text(), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_experiments_status", "experiments", ["status"], unique=False
    )

    op.create_table(
        "ab_assignments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("subject_type", sa.String(), nullable=False),
        sa.Column("subject_id", sa.String(), nullable=False),
        sa.Column(
            "experiment_key",
            sa.String(),
            sa.ForeignKey("experiments.key", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("variant", sa.String(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "subject_type",
            "subject_id",
            "experiment_key",
            name="uq_ab_assignments_subject_experiment",
        ),
    )
    op.create_index(
        "ix_ab_assignments_subject_id", "ab_assignments", ["subject_id"], unique=False
    )
    op.create_index(
        "ix_ab_assignments_experiment_key",
        "ab_assignments",
        ["experiment_key"],
        unique=False,
    )

    op.create_table(
        "metrics_daily",
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("meta_json", sa.Text(), nullable=False),
    )

    op.create_table(
        "funnel_daily",
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("funnel_name", sa.String(), primary_key=True),
        sa.Column("step", sa.String(), primary_key=True),
        sa.Column("users_count", sa.Integer(), nullable=False),
        sa.Column("meta_json", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("funnel_daily")
    op.drop_table("metrics_daily")

    op.drop_index("ix_ab_assignments_experiment_key", table_name="ab_assignments")
    op.drop_index("ix_ab_assignments_subject_id", table_name="ab_assignments")
    op.drop_table("ab_assignments")

    op.drop_index("ix_experiments_status", table_name="experiments")
    op.drop_table("experiments")

