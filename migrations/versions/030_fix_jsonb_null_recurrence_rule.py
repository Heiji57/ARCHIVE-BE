"""fix jsonb null recurrence_rule rows

SQLAlchemy JSONB without none_as_null=True stores Python None as 'null'::jsonb
instead of SQL NULL. This migration converts existing 'null'::jsonb rows to SQL NULL
so that IS NOT NULL filters work correctly.

Revision ID: 030
Revises: 029
Create Date: 2026-07-20
"""
from typing import Sequence, Union
from alembic import op

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE todos SET recurrence_rule = NULL WHERE recurrence_rule = 'null'::jsonb"
    )


def downgrade() -> None:
    pass  # 복원 불필요 — null 로 정정된 값을 다시 'null'::jsonb 로 되돌리지 않는다
