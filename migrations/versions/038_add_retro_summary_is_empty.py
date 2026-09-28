"""retro_summaries.is_empty — 소스 없는 기간은 AI 호출 없이 완료

회고·할일이 없는 기간(자동 요약 대상이지만 활동이 없는 사용자 등)에 Gemini 를 호출하던
비용을 없앤다. 워커가 안내 문구로 COMPLETED 처리하고 이 플래그를 세운다. 상위 요약
(월간/연간)은 플래그가 선 하위 요약을 입력으로 쓰지 않는다 — 안내 문구가 LLM 입력으로
들어가거나, 나중에 과거 날짜로 쓴 회고가 무시되지 않게 하기 위해서다.

기존 행은 모두 AI 가 실제로 쓴 요약이므로 false.

Revision ID: 038
Revises: 037
Create Date: 2026-09-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "038"
down_revision: Union[str, None] = "037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "retro_summaries",
        sa.Column("is_empty", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("retro_summaries", "is_empty")
