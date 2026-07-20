"""add calendar_auto_delete_todo to user_settings

Revision ID: 025
Revises: 024
Create Date: 2026-07-06

목적:
  Google Calendar 원본 이벤트를 ARCHIVE todo 로 승격하는 기능 도입에 맞춰,
  해당 이벤트가 Google 쪽에서 cancelled 되었을 때의 처리 방식을 사용자가 선택할 수
  있게 한다.

  user_settings.calendar_auto_delete_todo:
    - false(기본, 보수적): 연동만 해제(calendar_push_status/google_event_id 등 초기화),
      todo 자체는 유지.
    - true(공격적): 연동된 todo 를 함께 삭제.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column(
            "calendar_auto_delete_todo",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "calendar_auto_delete_todo")
