"""add account_type to users table

Revision ID: 019
Revises: 018
Create Date: 2026-06-22

목적:
  users 테이블에 account_type 컬럼을 추가한다.
  developer = GitHub 연동 기능 활성화, user = 기본 경험 (기본값).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "account_type",
            sa.String(length=16),
            nullable=False,
            server_default="user",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "account_type")