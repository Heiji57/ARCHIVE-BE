"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("totp_secret", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "todos",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("title_tsv", postgresql.TSVECTOR(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("date_key", sa.String(10), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_todos_user_id_date_key", "todos", ["user_id", "date_key"])
    op.create_index("ix_todos_title_tsv", "todos", ["title_tsv"], postgresql_using="gin")

    op.create_table(
        "journal_entries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("date_key", sa.String(10), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_tsv", postgresql.TSVECTOR(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date_key", name="uq_journal_entries_user_date"),
    )
    op.create_index("ix_journal_entries_user_id_date_key", "journal_entries", ["user_id", "date_key"])
    op.create_index(
        "ix_journal_entries_content_tsv", "journal_entries", ["content_tsv"], postgresql_using="gin"
    )

    op.create_table(
        "retro_summaries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("summary_type", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "summary_type", "period_start", name="uq_retro_summaries_user_type_period"
        ),
    )
    op.create_index("ix_retro_summaries_user_id", "retro_summaries", ["user_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id_is_read", "notifications", ["user_id", "is_read"])

    # tsvector 자동 갱신 트리거 — 'simple' 설정은 한국어 포함 다국어에 적합 (어간 처리 없이 토큰 분리)
    op.execute("""
        CREATE OR REPLACE FUNCTION update_todo_tsv() RETURNS trigger AS $$
        BEGIN
            NEW.title_tsv := to_tsvector('simple', NEW.title);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER todo_tsv_update
        BEFORE INSERT OR UPDATE ON todos
        FOR EACH ROW EXECUTE FUNCTION update_todo_tsv();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION update_journal_entry_tsv() RETURNS trigger AS $$
        BEGIN
            NEW.content_tsv := to_tsvector('simple', NEW.title || ' ' || NEW.content);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER journal_entry_tsv_update
        BEFORE INSERT OR UPDATE ON journal_entries
        FOR EACH ROW EXECUTE FUNCTION update_journal_entry_tsv();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS journal_entry_tsv_update ON journal_entries;")
    op.execute("DROP FUNCTION IF EXISTS update_journal_entry_tsv;")
    op.execute("DROP TRIGGER IF EXISTS todo_tsv_update ON todos;")
    op.execute("DROP FUNCTION IF EXISTS update_todo_tsv;")

    op.drop_table("notifications")
    op.drop_table("retro_summaries")
    op.drop_table("journal_entries")
    op.drop_table("todos")
    op.drop_table("users")
