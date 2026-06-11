"""add start_time / end_time columns to todos

Revision ID: 016
Revises: 015
Create Date: 2026-06-11

목적:
  FE 의 일일 타임라인(타임블록) 표시를 위해 Todo 에 선택적 시작/종료 시각을
  부여한다. 형식은 "HH:mm" 24시간제 문자열 — 사용자 로컬 표시 전용이므로
  PostgreSQL TIME 대신 VARCHAR(5) 로 저장한다 (직렬화 형식 일관성).

  두 필드는 독립적으로 nullable. 한쪽만 설정하는 케이스(예: 시작만)는 허용.
  교차 검증 (end > start) 은 application/presentation 레이어에서 처리.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "todos",
        sa.Column("start_time", sa.String(length=5), nullable=True),
    )
    op.add_column(
        "todos",
        sa.Column("end_time", sa.String(length=5), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("todos", "end_time")
    op.drop_column("todos", "start_time")
