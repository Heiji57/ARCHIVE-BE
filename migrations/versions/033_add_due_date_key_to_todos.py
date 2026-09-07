"""add due_date_key column to todos

Revision ID: 033
Revises: 032
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("todos", sa.Column("due_date_key", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("todos", "due_date_key")
