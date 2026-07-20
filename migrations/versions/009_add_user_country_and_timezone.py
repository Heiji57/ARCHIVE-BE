"""add country, region, timezone to users + last_summary_date_local to user_settings

Revision ID: 009
Revises: 008
Create Date: 2026-06-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users 테이블 — country/region/timezone 추가
    op.add_column(
        "users",
        sa.Column("country", sa.String(2), nullable=False, server_default="KR"),
    )
    op.add_column(
        "users",
        sa.Column("region", sa.String(8), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Seoul"),
    )
    # 기존 사용자 backfill 후 server_default 제거 (이후 신규는 명시 입력 필수)
    op.alter_column("users", "country", server_default=None)
    op.alter_column("users", "timezone", server_default=None)

    op.create_index("ix_users_timezone", "users", ["timezone"])

    # user_settings 테이블 — DST 중복 방지용 last_summary_date_local
    op.add_column(
        "user_settings",
        sa.Column("last_summary_date_local", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "last_summary_date_local")
    op.drop_index("ix_users_timezone", table_name="users")
    op.drop_column("users", "timezone")
    op.drop_column("users", "region")
    op.drop_column("users", "country")
