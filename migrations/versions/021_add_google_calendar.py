"""add google_calendar_connections and calendar_events tables

Revision ID: 021
Revises: 020
Create Date: 2026-06-27

목적:
  Google Calendar 연동 — 연결 정보(refresh_token 포함)와 동기화된 이벤트를 영속화.
  - google_calendar_connections: 1 user : 1 connection. refresh_token 으로 백그라운드
    AI 요약 시점에도 토큰 갱신 가능. sync_token 으로 증분 동기화.
  - calendar_events: 동기화된 이벤트 스냅샷. (user_id, google_event_id) 유니크 upsert.
    시간 표현은 todo 와 동일(start_at/end_at TIMESTAMPTZ + timezone 스냅샷, all_day/date_key).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "google_calendar_connections",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("google_user_id", sa.String(length=255), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("sync_token", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("needs_reauth", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_google_calendar_connections_user"),
    )

    op.create_table(
        "calendar_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.String(), nullable=False),
        sa.Column("google_event_id", sa.String(length=1024), nullable=False),
        sa.Column("calendar_id", sa.String(length=512), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("date_key", sa.String(length=10), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="confirmed"),
        sa.Column("html_link", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "google_event_id", name="uq_calendar_events_user_event"),
    )
    op.create_index("ix_calendar_events_user_date", "calendar_events", ["user_id", "date_key"])


def downgrade() -> None:
    op.drop_index("ix_calendar_events_user_date", table_name="calendar_events")
    op.drop_table("calendar_events")
    op.drop_table("google_calendar_connections")
