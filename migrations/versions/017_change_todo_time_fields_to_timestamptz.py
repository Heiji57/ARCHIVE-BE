"""change todo start_time/end_time to TIMESTAMPTZ and add timezone column

Revision ID: 017
Revises: 016
Create Date: 2026-06-18

목적:
  start_time / end_time 을 "HH:mm" VARCHAR(5) 에서 UTC TIMESTAMPTZ 로 변경하고,
  사용자 로컬 시각 복원을 위한 IANA timezone 컬럼을 추가한다.

  기존 VARCHAR(5) 데이터는 UTC timestamp 로 변환 불가능하므로 NULL 로 초기화.
  timezone 컬럼은 start_time / end_time 이 null 이면 null.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("todos", "start_time")
    op.drop_column("todos", "end_time")
    op.add_column("todos", sa.Column("start_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column("todos", sa.Column("end_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column("todos", sa.Column("timezone", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("todos", "timezone")
    op.drop_column("todos", "end_time")
    op.drop_column("todos", "start_time")
    op.add_column("todos", sa.Column("start_time", sa.String(length=5), nullable=True))
    op.add_column("todos", sa.Column("end_time", sa.String(length=5), nullable=True))
