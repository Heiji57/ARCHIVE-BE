"""AI 비서 5c — 설정(ai_settings), 알려 둔 것(ai_memories), 예약한 일(ai_schedules)

설정 행이 없으면 도메인 기본값(모든 도구 켬, 확인 항상, 보통 길이, 기억 켬, 90일 보관)을 쓴다.

Revision ID: 046
Revises: 045
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "046"
down_revision: Union[str, None] = "045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = postgresql.JSONB(astext_type=sa.Text())


def _user_fk() -> sa.ForeignKey:
    return sa.ForeignKey("users.id", ondelete="CASCADE")


def upgrade() -> None:
    op.create_table(
        "ai_settings",
        sa.Column("user_id", sa.String(), _user_fk(), primary_key=True),
        sa.Column("pet_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("tools", _JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("confirm_mode", sa.String(10), nullable=False, server_default="always"),
        sa.Column("answer_length", sa.String(10), nullable=False, server_default="normal"),
        sa.Column("deep_search", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("memory_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default=sa.text("90")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "ai_memories",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), _user_fk(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_memories_user", "ai_memories", ["user_id"])
    op.create_table(
        "ai_schedules",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), _user_fk(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("repeat", _JSONB, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_run_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_schedules_user", "ai_schedules", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_schedules_user", table_name="ai_schedules")
    op.drop_table("ai_schedules")
    op.drop_index("ix_ai_memories_user", table_name="ai_memories")
    op.drop_table("ai_memories")
    op.drop_table("ai_settings")
