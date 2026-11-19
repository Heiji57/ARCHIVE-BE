"""내보내기 작업(exports) — 사용자당 진행 중 하나(부분 유니크), 최근 24시간 3번

Revision ID: 048
Revises: 047
Create Date: 2026-11-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "048"
down_revision: Union[str, None] = "047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exports",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("scopes", postgresql.ARRAY(sa.String(10)), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("file_key", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_exports_user_created", "exports", ["user_id", "created_at"])
    op.create_index(
        "uq_exports_user_pending",
        "exports",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_exports_user_pending", table_name="exports")
    op.drop_index("ix_exports_user_created", table_name="exports")
    op.drop_table("exports")
