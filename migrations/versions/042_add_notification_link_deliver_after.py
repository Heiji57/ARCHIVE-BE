"""notifications.link(누르면 이동할 곳), deliver_after(방해 금지 보류 시각)

category 는 문자열 컬럼이라 새 종류(due/schedule/ai)에 마이그레이션이 필요 없다.

Revision ID: 042
Revises: 041
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "042"
down_revision: Union[str, None] = "041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("link", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("deliver_after", sa.DateTime(timezone=True), nullable=True),
    )
    # flush 작업은 보류 중인 알림만 훑는다 — 대부분 NULL 이라 부분 인덱스가 작다.
    op.create_index(
        "ix_notifications_deliver_after",
        "notifications",
        ["deliver_after"],
        postgresql_where=sa.text("deliver_after IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_deliver_after", table_name="notifications")
    op.drop_column("notifications", "deliver_after")
    op.drop_column("notifications", "link")
