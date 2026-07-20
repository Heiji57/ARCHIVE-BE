"""add recurrence fields to todos

Revision ID: 029
Revises: 028
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("todos", sa.Column("recurrence_rule", JSONB(), nullable=True))
    op.add_column("todos", sa.Column("series_id", sa.String(64), nullable=True))
    op.add_column("todos", sa.Column("original_date_key", sa.String(10), nullable=True))
    op.add_column("todos", sa.Column("original_start_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column("todos", sa.Column("master_google_event_id", sa.String(1024), nullable=True))

    op.create_index(
        "ix_todos_series_id",
        "todos",
        ["series_id"],
        postgresql_where=sa.text("series_id IS NOT NULL"),
    )
    op.create_index(
        "uq_todos_series_original_date",
        "todos",
        ["series_id", "original_date_key"],
        unique=True,
        postgresql_where=sa.text("series_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_todos_series_original_date", table_name="todos")
    op.drop_index("ix_todos_series_id", table_name="todos")
    op.drop_column("todos", "master_google_event_id")
    op.drop_column("todos", "original_start_time")
    op.drop_column("todos", "original_date_key")
    op.drop_column("todos", "series_id")
    op.drop_column("todos", "recurrence_rule")
