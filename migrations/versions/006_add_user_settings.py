"""add user_settings table

Revision ID: 006
Revises: 005
Create Date: 2026-05-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("locale", sa.String(10), nullable=False, server_default="ko"),
        sa.Column("auto_summary_weekly", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("auto_summary_monthly", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("auto_summary_yearly", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notification_retention_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("last_schedule_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_settings")
