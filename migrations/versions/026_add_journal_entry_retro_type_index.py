"""add (user_id, retro_type, date_key) composite index to journal_entries

Revision ID: 026
Revises: 025
Create Date: 2026-07-07

목적:
  GET /entries?retroType=... 및 신규 GET /entries/paginated 가 retro_type 으로
  필터링하는데, 기존 ix_journal_entries_user_id_date_key 는 retro_type 을 포함하지
  않아 인덱스를 못 탔다. 사용자가 오래 쓸수록(수백~수천 건) 이 필터가 자주 실행되는
  경로가 되므로 복합 인덱스를 추가한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_journal_entries_user_id_retro_type_date_key",
        "journal_entries",
        ["user_id", "retro_type", "date_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_journal_entries_user_id_retro_type_date_key", table_name="journal_entries")
