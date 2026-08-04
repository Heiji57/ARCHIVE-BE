"""add tag column to todos

Revision ID: 031
Revises: 030
Create Date: 2026-08-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("todos", sa.Column("tag", sa.String(20), nullable=True))
    op.create_index(
        "ix_todos_user_tag",
        "todos",
        ["user_id", "tag"],
        postgresql_where=sa.text("tag IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_todos_user_tag", table_name="todos")
    op.drop_column("todos", "tag")
