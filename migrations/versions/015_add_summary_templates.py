"""add user_summary_templates table + active_summary_template_ids on user_settings

Revision ID: 015
Revises: 014
Create Date: 2026-06-10

목적:
  사용자가 weekly / monthly / annual 자동 요약 출력 형식을 위해 **여러 개**의
  markdown 템플릿을 만들고, summary_type 별로 하나를 활성으로 선택할 수 있게 한다.

  설계 (A안):
    user_summary_templates  : 사용자의 템플릿 풀 (summary_type 별로 분리)
    user_settings.active_summary_template_ids :
      summary_type → 활성 template id 매핑 (JSONB)
      키 부재 / null  → 시스템 기본 템플릿 사용

  제약:
    (user_id, summary_type, name) UNIQUE — 같은 type 안에서 이름 중복 금지
    한 (user, summary_type) 당 최대 N (env: SUMMARY_TEMPLATE_MAX_PER_TYPE, 기본 5)
      는 use case 에서 검증 (DB 제약으로 두지 않음 — env 변경 용이성 우선)
    content max 4000자 — Pydantic 검증

  삭제 정책:
    활성 템플릿은 use case 에서 삭제 차단 (FK 로 차단하지 않음 — 다국적 cleanup
    플로우 단순화). DELETE 시 활성 ID 매칭되면 InUseException raise.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_summary_templates",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("summary_type", sa.String(16), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_summary_templates_user_type",
        "user_summary_templates",
        ["user_id", "summary_type"],
    )
    op.create_index(
        "uq_user_summary_templates_user_type_name",
        "user_summary_templates",
        ["user_id", "summary_type", "name"],
        unique=True,
    )

    op.add_column(
        "user_settings",
        sa.Column(
            "active_summary_template_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "active_summary_template_ids")
    op.drop_index("uq_user_summary_templates_user_type_name",
                  table_name="user_summary_templates")
    op.drop_index("ix_user_summary_templates_user_type",
                  table_name="user_summary_templates")
    op.drop_table("user_summary_templates")
