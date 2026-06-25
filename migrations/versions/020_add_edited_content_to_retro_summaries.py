"""add edited_content to retro_summaries

Revision ID: 020
Revises: 019
Create Date: 2026-06-24

목적:
  retro_summaries 에 사용자 편집 마크다운 오버라이드 컬럼(edited_content)을 추가한다.
  AI 원본(content JSONB)은 비파괴 보존되며, edited_content 가 있으면 FE 가 우선 렌더한다.
  재생성(force/FAILED/auto) 시 use case / dispatcher 가 NULL 로 초기화한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "retro_summaries",
        sa.Column("edited_content", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("retro_summaries", "edited_content")
