"""add provider_login to oauth_connections

Revision ID: 012
Revises: 011
Create Date: 2026-06-08

목적:
  GitHub OAuth `login` (사용자명) 을 OAuthConnection 에 캐싱.
  `GET /github/commits` 등에서 매 호출마다 /user API 를 치지 않도록.
  NULL 허용 — 기존 row 는 다음 호출 시점에 lazy backfill.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "oauth_connections",
        sa.Column("provider_login", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("oauth_connections", "provider_login")
