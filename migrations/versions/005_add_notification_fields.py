"""add type, category, title to notifications

Revision ID: 005
Revises: 004
Create Date: 2026-05-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("type", sa.String(20), nullable=False, server_default="info"))
    op.add_column("notifications", sa.Column("category", sa.String(20), nullable=False, server_default="system"))
    op.add_column("notifications", sa.Column("title", sa.String(255), nullable=False, server_default=""))

    op.alter_column("notifications", "type", server_default=None)
    op.alter_column("notifications", "category", server_default=None)
    op.alter_column("notifications", "title", server_default=None)


def downgrade() -> None:
    op.drop_column("notifications", "title")
    op.drop_column("notifications", "category")
    op.drop_column("notifications", "type")
