"""change todos.tag (single) to todos.tags (array)

Revision ID: 032
Revises: 031
Create Date: 2026-08-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "todos",
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String(20)),
            nullable=False,
            server_default="{}",
        ),
    )
    op.execute(
        "UPDATE todos SET tags = ARRAY[tag] WHERE tag IS NOT NULL"
    )
    op.drop_index("ix_todos_user_tag", table_name="todos")
    op.drop_column("todos", "tag")
    op.create_index(
        "ix_todos_tags_gin",
        "todos",
        ["tags"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_todos_tags_gin", table_name="todos")
    op.add_column("todos", sa.Column("tag", sa.String(20), nullable=True))
    op.execute(
        "UPDATE todos SET tag = tags[1] WHERE cardinality(tags) > 0"
    )
    op.create_index(
        "ix_todos_user_tag",
        "todos",
        ["user_id", "tag"],
        postgresql_where=sa.text("tag IS NOT NULL"),
    )
    op.drop_column("todos", "tags")
