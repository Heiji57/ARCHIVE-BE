"""add provider_verified_emails to oauth_connections

Revision ID: 014
Revises: 013
Create Date: 2026-06-09

목적:
  GitHub 계정의 verified emails 목록을 OAuthConnection 에 캐싱.
  `GET /github/commits` 에서 author/committer email 매칭에 사용 — gitbash 등
  로컬 git config email 이 GitHub 에 verified 로 등록돼 있으면 commit 이 잡힘.
  NULL 허용 — 다음 호출 시점에 lazy backfill (`/user/emails` API).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "oauth_connections",
        sa.Column(
            "provider_verified_emails",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("oauth_connections", "provider_verified_emails")
