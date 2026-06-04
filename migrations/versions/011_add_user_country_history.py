"""add user_country_history table + backfill existing users

Revision ID: 011
Revises: 010
Create Date: 2026-06-04

목적:
  사용자별 국가/지역/타임존 변경 이력을 통계/분석 용도로 보존.
  source 컬럼: 'registration' | 'oauth_onboarding' | 'settings_update'.
  기존 모든 유저는 현재 country/region/timezone 으로 'registration' 1행을 backfill 한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_country_history",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("region", sa.String(8), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_uch_user_id_created_at",
        "user_country_history",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_uch_country_created_at",
        "user_country_history",
        ["country", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_uch_created_at",
        "user_country_history",
        ["created_at"],
    )

    # 기존 유저 backfill — ID 포맷: "uch_" + 32 hex chars (uuid7 와 동일 길이)
    # md5(random()::text || user_id) 으로 32 hex 보장 — pgcrypto 의존 없음
    op.execute(
        """
        INSERT INTO user_country_history
            (id, user_id, country, region, timezone, source, created_at)
        SELECT
            'uch_' || md5(random()::text || id),
            id,
            country,
            region,
            timezone,
            'registration',
            created_at
        FROM users
        """
    )


def downgrade() -> None:
    op.drop_index("ix_uch_created_at", table_name="user_country_history")
    op.drop_index("ix_uch_country_created_at", table_name="user_country_history")
    op.drop_index("ix_uch_user_id_created_at", table_name="user_country_history")
    op.drop_table("user_country_history")
