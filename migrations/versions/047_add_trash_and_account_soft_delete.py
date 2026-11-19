"""휴지통(todos·journal_entries.deleted_at)과 계정 soft delete(users.deleted_at), 프로필 이름·사진

- deleted_at 이 채워진 행은 모든 ORM 조회에서 빠진다(shared/infrastructure/database/soft_delete.py).
- 유일 조건은 지우지 않은 행끼리만 — 휴지통의 회고가 같은 날 새 회고를, 지운 계정의 이메일이
  새 가입을 막지 않게 부분 유니크 인덱스로 바꾼다.

Revision ID: 047
Revises: 046
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "047"
down_revision: Union[str, None] = "046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("todos", "journal_entries"):
        op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index(f"ix_{table}_user_deleted", table, ["user_id", "deleted_at"])

    op.drop_constraint("uq_journal_entries_user_date_retro_type", "journal_entries", type_="unique")
    op.create_index(
        "uq_journal_entries_user_date_retro_type",
        "journal_entries",
        ["user_id", "date_key", "retro_type"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.add_column("users", sa.Column("display_name", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("avatar_key", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.create_index(
        "uq_users_email_active",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_email_active", table_name="users")
    op.create_unique_constraint("users_email_key", "users", ["email"])
    for col in ("deleted_at", "avatar_key", "display_name"):
        op.drop_column("users", col)
    op.drop_index("uq_journal_entries_user_date_retro_type", table_name="journal_entries")
    op.create_unique_constraint(
        "uq_journal_entries_user_date_retro_type",
        "journal_entries",
        ["user_id", "date_key", "retro_type"],
    )
    for table in ("journal_entries", "todos"):
        op.drop_index(f"ix_{table}_user_deleted", table_name=table)
        op.drop_column(table, "deleted_at")
