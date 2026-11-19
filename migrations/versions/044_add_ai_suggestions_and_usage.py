"""AI 비서 5a — 규칙 기반 추천(ai_suggestions)과 사용량(ai_usage)

- ai_suggestions: 같은 날 같은 (종류, 할 일) 은 한 행 — 넘긴 추천이 다시 나오지 않게 상태를 이어 쓴다.
  todo_id 는 가상 반복 회차 id("{base}::{date}")도 담으므로 FK 를 걸지 않는다.
- ai_usage: 사용자 tz 날짜별 요청·토큰 수(하루·한 달 상한 계산).

Revision ID: 044
Revises: 043
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "044"
down_revision: Union[str, None] = "043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_suggestions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("date_key", sa.String(10), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("todo_id", sa.String(128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("applied", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "date_key", "kind", "todo_id", name="uq_ai_suggestions_key"),
    )
    op.create_index("ix_ai_suggestions_user_date", "ai_suggestions", ["user_id", "date_key"])
    op.create_table(
        "ai_usage",
        sa.Column(
            "user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("date_key", sa.String(10), primary_key=True),
        sa.Column("requests", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_table("ai_usage")
    op.drop_index("ix_ai_suggestions_user_date", table_name="ai_suggestions")
    op.drop_table("ai_suggestions")
