"""topic_digests 증분 재생성 상태 컬럼

재생성을 "이전 digest 본문 + 마지막 생성 이후 새로 임베딩된 청크" 병합(증분)으로 바꾸면서,
언제 전체 재생성으로 되돌릴지 판정할 상태를 저장한다.

- last_generated_at: 증분 커서. watermark_date_key(날짜)로는 정리 당일 이후에 쓴 회고를
  구분할 수 없어 시각을 따로 둔다. 청크 created_at(재임베딩 시각)과 비교한다.
- incremental_count: 마지막 전체 재생성 이후 연속 증분 횟수 — 요약 위에 요약이 쌓이는
  drift 를 주기적으로 리셋하는 기준.
- full_fingerprint: 주제 이름·설명·프롬프트 버전·모델·검색 설정 해시 — 바뀌면 전체 재생성.
- source_entry_ids: 현재 본문에 반영된 회고 id — 과거 회고 수정·삭제 감지용.

기존 행은 last_generated_at 이 NULL 이라 다음 생성이 자동으로 전체 재생성이 된다.

Revision ID: 037
Revises: 036
Create Date: 2026-09-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "037"
down_revision: Union[str, None] = "036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "topic_digests",
        sa.Column("last_generated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "topic_digests",
        sa.Column("incremental_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "topic_digests",
        sa.Column("full_fingerprint", sa.String(40), nullable=True),
    )
    op.add_column(
        "topic_digests",
        sa.Column(
            "source_entry_ids",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("topic_digests", "source_entry_ids")
    op.drop_column("topic_digests", "full_fingerprint")
    op.drop_column("topic_digests", "incremental_count")
    op.drop_column("topic_digests", "last_generated_at")
