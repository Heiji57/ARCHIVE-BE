"""user_settings 리디자인 설정 — 주 시작 요일, 일하는 시간, 알림·방해 금지, 화면 설정

JSONB 값은 빈 객체로 두면 도메인 기본값이 채워진다(`WorkSchedule.from_dict` 등) — 기존 행은
마이그레이션 없이 기본값으로 동작한다. last_*_date 는 예약 알림·주간 이메일 중복 발송 방지.

Revision ID: 041
Revises: 040
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "041"
down_revision: Union[str, None] = "040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB_COLUMNS = (
    "work_schedule",
    "day_end_reminder",
    "notification_prefs",
    "quiet_hours",
    "ui_preferences",
)
_DATE_COLUMNS = ("last_due_reminder_date", "last_day_end_reminder_date", "last_weekly_email_date")


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("week_start", sa.String(3), nullable=False, server_default="mon"),
    )
    op.add_column(
        "user_settings",
        sa.Column("default_todo_minutes", sa.Integer(), nullable=False, server_default="60"),
    )
    op.add_column(
        "user_settings",
        sa.Column("email_digest", sa.String(10), nullable=False, server_default="off"),
    )
    for name in _JSONB_COLUMNS:
        op.add_column(
            "user_settings",
            sa.Column(
                name,
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
    for name in _DATE_COLUMNS:
        op.add_column("user_settings", sa.Column(name, sa.Date(), nullable=True))


def downgrade() -> None:
    for name in (*_DATE_COLUMNS, *_JSONB_COLUMNS, "email_digest", "default_todo_minutes", "week_start"):
        op.drop_column("user_settings", name)
