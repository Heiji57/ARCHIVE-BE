"""remove totp columns from users

Revision ID: 007
Revises: 006
Create Date: 2026-05-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("users", "totp_secret")
    op.drop_column("users", "totp_enabled")


def downgrade() -> None:
    op.add_column("users", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("totp_secret", sa.String(64), nullable=True))
    op.alter_column("users", "totp_enabled", server_default=None)
