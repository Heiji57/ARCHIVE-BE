"""add retrospective_pushes table

Revision ID: 013
Revises: 012
Create Date: 2026-06-08

목적:
  GitHub 에 push 된 회고록을 (user_id, period_type, period_key) 단위로 기록.
  JournalEntry / RetroSummary 어느 쪽에서 push 되었든 동일 period 면 같은 row.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "retrospective_pushes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_type", sa.String(16), nullable=False),
        sa.Column("period_key", sa.String(32), nullable=False),
        sa.Column("repository_id", sa.String(), nullable=False),
        sa.Column("repository_full_name", sa.String(255), nullable=False),
        sa.Column("path", sa.String(512), nullable=False),
        sa.Column("commit_sha", sa.String(64), nullable=False),
        sa.Column("html_url", sa.Text(), nullable=False),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "user_id", "period_type", "period_key",
            name="uq_retro_pushes_user_period",
        ),
    )
    op.create_index(
        "ix_retro_pushes_user_pushed_at",
        "retrospective_pushes",
        ["user_id", "pushed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_retro_pushes_user_pushed_at", table_name="retrospective_pushes")
    op.drop_table("retrospective_pushes")
