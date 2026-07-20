"""add retro_type to journal_entries

Revision ID: 002
Revises: 001
Create Date: 2026-05-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "journal_entries",
        sa.Column("retro_type", sa.String(20), nullable=False, server_default="daily"),
    )
    op.create_index("ix_journal_entries_user_id_retro_type", "journal_entries", ["user_id", "retro_type"])


def downgrade() -> None:
    op.drop_index("ix_journal_entries_user_id_retro_type", table_name="journal_entries")
    op.drop_column("journal_entries", "retro_type")
