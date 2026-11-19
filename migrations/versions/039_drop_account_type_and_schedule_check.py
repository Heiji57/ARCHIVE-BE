"""users.account_type, user_settings.last_schedule_check_at 제거

- account_type: 개발자/일반 계정 구분을 없앴다. GitHub 기능은 GitHub 연결 여부로만 판단한다.
- last_schedule_check_at: FE 로컬 자동요약 스케줄러용 값이었다. 자동 요약은 서버
  (`last_summary_date_local`)가 맡고 있어 읽는 곳이 없다.

Revision ID: 039
Revises: 038
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "039"
down_revision: Union[str, None] = "038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("users", "account_type")
    op.drop_column("user_settings", "last_schedule_check_at")


def downgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("last_schedule_check_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("account_type", sa.String(16), nullable=False, server_default="user"),
    )
