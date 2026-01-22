"""discord oauth fields

Revision ID: 0013_discord_oauth
Revises: 0012_challenges
Create Date: 2026-01-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_discord_oauth"
down_revision = "0012_challenges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("discord_id", sa.String(), nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.String(), nullable=True))
    op.create_index("ix_users_discord_id", "users", ["discord_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_discord_id", table_name="users")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "discord_id")

