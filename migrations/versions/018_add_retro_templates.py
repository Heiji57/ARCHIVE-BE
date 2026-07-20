"""add retro_templates table and active_retro_template_ids to user_settings

Revision ID: 018
Revises: 017
Create Date: 2026-06-18

목적:
  회고 작성 시 초기값으로 사용하는 마크다운 템플릿을 서버에 영속화한다.
  - retro_templates 테이블: 사용자별 회고 템플릿 (daily/weekly/monthly/yearly)
  - user_settings.active_retro_template_ids: retro_type → 활성 template_id 매핑 (JSONB)

  기본 4종 템플릿(is_default=true) 은 회원가입/온보딩 시 애플리케이션 레이어에서 시드.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "retro_templates",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("retro_type", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_retro_templates_user_type", "retro_templates", ["user_id", "retro_type"])

    op.add_column(
        "user_settings",
        sa.Column(
            "active_retro_template_ids",
            JSONB(),
            nullable=False,
            server_default=text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "active_retro_template_ids")
    op.drop_index("ix_retro_templates_user_type", table_name="retro_templates")
    op.drop_table("retro_templates")
