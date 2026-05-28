"""fix journal_entry unique constraint to include retro_type

Revision ID: 004
Revises: 003
Create Date: 2026-05-28

"""
from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_journal_entries_user_date", "journal_entries", type_="unique")
    op.create_unique_constraint(
        "uq_journal_entries_user_date_retro_type",
        "journal_entries",
        ["user_id", "date_key", "retro_type"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_journal_entries_user_date_retro_type", "journal_entries", type_="unique")
    op.create_unique_constraint(
        "uq_journal_entries_user_date",
        "journal_entries",
        ["user_id", "date_key"],
    )
