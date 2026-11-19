"""AI 비서 5b — 대화(ai_conversations), 메시지(ai_messages), 제안(ai_proposals)

제안은 사용자가 적용하기 전에는 아무것도 바꾸지 않는다. applied 에 적용 결과(만든·바꾼 id,
이전 값)를 남겨 되돌리기에 쓴다. 대화를 지우면 메시지는 함께 지워지고(CASCADE) 제안은
conversation_id 만 비운다(SET NULL — 적용한 제안의 되돌리기 기록은 남긴다).

Revision ID: 045
Revises: 044
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "045"
down_revision: Union[str, None] = "044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "ai_conversations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.String(200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_conversations_user", "ai_conversations", ["user_id", "updated_at"])
    op.create_table(
        "ai_messages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(),
            sa.ForeignKey("ai_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", _JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("context", _JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ai_messages_conversation", "ai_messages", ["conversation_id", "created_at"]
    )
    op.create_table(
        "ai_proposals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "conversation_id",
            sa.String(),
            sa.ForeignKey("ai_conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("payload", _JSONB, nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("applied", _JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_proposals_conversation", "ai_proposals", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_proposals_conversation", table_name="ai_proposals")
    op.drop_table("ai_proposals")
    op.drop_index("ix_ai_messages_conversation", table_name="ai_messages")
    op.drop_table("ai_messages")
    op.drop_index("ix_ai_conversations_user", table_name="ai_conversations")
    op.drop_table("ai_conversations")
