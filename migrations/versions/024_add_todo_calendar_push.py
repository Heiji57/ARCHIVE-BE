"""add calendar-push fields to todos + calendar_auto_push_todo to user_settings

Revision ID: 024
Revises: 023
Create Date: 2026-07-03

목적:
  ARCHIVE → Google Calendar 단방향 push (양방향 동기화의 push 절반).
  todos 를 만들거나 수정/삭제하면 Google Calendar 에도 반영한다.

  todos 컬럼:
    - calendar_push_status: NULL(미연동) | pending | syncing | synced | failed | pending_delete
    - google_event_id: 매핑된 Google 이벤트 id (push 성공 후 세팅)
    - push_intent: 'push' | 'delete' — 사용자 의도(콘텐츠 반영 vs 연동 해제). claim/finalize
      가 status 를 'syncing' 으로 덮어써도 원래 의도가 보존되도록 상태와 분리.
    - push_started_at: claim(또는 per-item heartbeat) 시각 — stuck 워커 감지 기준.
    - sync_attempt_id: claim 마다 발급하는 optimistic-lock 토큰. finalize 는 이 토큰이
      여전히 일치할 때만 반영 → 사용자 편집/재claim 과의 lost-update 방지.
    - push_retry_count: 실패 재시도 횟수. 상한 도달 시 claim 제외(무한 재시도 방지).

  ix_todos_calendar_push: claim 후보 스캔(user_id 필터 + updated_at 정렬)을 위한 부분 인덱스.

  user_settings.calendar_auto_push_todo: 신규 todo 생성 시 기본으로 캘린더에 push 할지.
    기본 false. 이미 연동된 todo 를 소급 변경하지는 않는다(생성 기본값 전용).

  기존 연결 재인증 강제:
    scope 가 calendar.readonly → calendar.events 로 확장되므로, 기존에 연결된 사용자는
    쓰기 권한이 없다. needs_reauth=true 로 마킹해 FE 가 재연결(권한 재동의)을 유도한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("todos", sa.Column("calendar_push_status", sa.String(length=20), nullable=True))
    op.add_column("todos", sa.Column("google_event_id", sa.String(length=1024), nullable=True))
    op.add_column("todos", sa.Column("push_intent", sa.String(length=10), nullable=True))
    op.add_column("todos", sa.Column("push_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("todos", sa.Column("sync_attempt_id", sa.String(length=64), nullable=True))
    op.add_column(
        "todos",
        sa.Column("push_retry_count", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    # claim 후보 스캔용 부분 인덱스 — 대다수 todo 는 캘린더 미연동(status NULL)이라 인덱스가 작다.
    op.create_index(
        "ix_todos_calendar_push",
        "todos",
        ["user_id", "updated_at"],
        postgresql_where=sa.text("calendar_push_status IS NOT NULL"),
    )

    op.add_column(
        "user_settings",
        sa.Column(
            "calendar_auto_push_todo",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    # scope 확장(readonly → events) 으로 기존 연결은 쓰기 권한 부재 → 재연결 강제.
    op.execute("UPDATE google_calendar_connections SET needs_reauth = true")


def downgrade() -> None:
    op.drop_column("user_settings", "calendar_auto_push_todo")
    op.drop_index("ix_todos_calendar_push", table_name="todos")
    op.drop_column("todos", "push_retry_count")
    op.drop_column("todos", "sync_attempt_id")
    op.drop_column("todos", "push_started_at")
    op.drop_column("todos", "push_intent")
    op.drop_column("todos", "google_event_id")
    op.drop_column("todos", "calendar_push_status")
