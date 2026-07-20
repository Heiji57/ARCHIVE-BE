"""add last_active_at to google_calendar_connections

Revision ID: 022
Revises: 021
Create Date: 2026-06-30

목적:
  백그라운드 주기 캘린더 동기화의 "활성 사용자" 판단 기준.
  - last_active_at: 사용자가 실제로 캘린더 데이터를 조회한 마지막 시각(요청 경로에서만 갱신).
    last_synced_at 은 sync 자체가 갱신하므로 활성도 신호로 쓸 수 없다(순환).
  - ix_gcal_conn_active: (needs_reauth, last_active_at) 복합 인덱스로 활성 사용자 조회 가속.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "google_calendar_connections",
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_gcal_conn_active",
        "google_calendar_connections",
        ["needs_reauth", "last_active_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_gcal_conn_active", table_name="google_calendar_connections")
    op.drop_column("google_calendar_connections", "last_active_at")
