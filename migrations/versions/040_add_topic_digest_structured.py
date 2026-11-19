"""topic_digests.structured — 구조화 주제 정리(큰 주제·날짜별 한 일·근거)

기존 정리는 NULL 로 남긴다(한꺼번에 다시 만들지 않는다 — 비용). 사용자가 다시 정리하면
채워지고, `_PROMPT_VERSION` 이 바뀌어 다음 정리는 전체 재생성이 된다.

Revision ID: 040
Revises: 039
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "040"
down_revision: Union[str, None] = "039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "topic_digests",
        sa.Column("structured", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("topic_digests", "structured")
