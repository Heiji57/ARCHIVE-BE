"""사용자 캘린더(calendars) + todos.calendar_id, 태그 색·순서(user_tags)

- calendars: 사용자마다 기본 캘린더가 정확히 하나(부분 유니크 인덱스). 기존 사용자에게 기본
  캘린더("default" — 표시 이름은 FE 가 locale 로)를 만든다. 기본 캘린더만 Google 로 보낸다.
- todos.calendar_id: NULL = 기본 캘린더. 캘린더를 지우면 SET NULL 로 기본 캘린더로 옮겨진다.
- user_tags: todos.tags 배열은 그대로 두고 색·순서만 담는 보조 테이블. 행이 없는 태그는
  FE 가 이름 해시 색을 쓴다.

Revision ID: 043
Revises: 042
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "043"
down_revision: Union[str, None] = "042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calendars",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("color", sa.String(8), nullable=False, server_default="c1"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("push_to_google", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "name", name="uq_calendars_user_name"),
    )
    op.create_index(
        "uq_calendars_user_default",
        "calendars",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    # 기존 사용자 기본 캘린더 — id 는 사용자별로 결정적으로 만든다(재실행해도 같은 값).
    op.execute(
        """
        INSERT INTO calendars (id, user_id, name, color, sort_order, is_default, push_to_google,
                               created_at)
        SELECT 'cal_default_' || md5(id), id, 'default', 'c1', 0, true, true, now()
        FROM users
        """
    )

    op.add_column(
        "todos",
        sa.Column(
            "calendar_id",
            sa.String(),
            sa.ForeignKey("calendars.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_todos_calendar_id", "todos", ["calendar_id"])

    op.create_table(
        "user_tags",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(20), nullable=False),
        sa.Column("color", sa.String(8), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_user_tags_user_name"),
    )


def downgrade() -> None:
    op.drop_table("user_tags")
    op.drop_index("ix_todos_calendar_id", table_name="todos")
    op.drop_column("todos", "calendar_id")
    op.drop_index("uq_calendars_user_default", table_name="calendars")
    op.drop_table("calendars")
