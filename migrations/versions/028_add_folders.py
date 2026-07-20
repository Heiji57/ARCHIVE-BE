"""add folders — nested folder organization for retrospectives

Revision ID: 028
Revises: 027
Create Date: 2026-07-12

목적:
  회고록(daily/weekly/monthly/yearly 전부)을 사용자가 폴더로 정리할 수 있게
  self-referencing folders 테이블을 추가하고, journal_entries/retro_summaries
  양쪽에 folder_id 를 연결한다. 트리는 adjacency list(부모 FK)로 저장한다 —
  개인 생산성 앱 스케일에서 materialized path/closure table 은 과설계.

  - folders.parent_folder_id ON DELETE SET NULL: 하위 폴더는 (조부모 승격 없이)
    바로 최상위로 orphan. 순환참조는 FK로 표현이 안 되므로 이동(rename/move)
    유스케이스에서 조상 체인을 순회해 애플리케이션 레벨로 방지한다.
  - journal_entries/retro_summaries.folder_id 도 동일하게 SET NULL — 폴더를
    지워도 안의 회고록은 삭제되지 않고 폴더 소속만 해제된다.
  - (user_id, COALESCE(parent_folder_id,''), name) 유니크 인덱스 — 같은 부모
    아래(최상위 포함) 이름 중복 금지. Postgres 유니크 제약은 NULL 을 서로 다른
    값으로 취급하므로 COALESCE 표현식 인덱스로 우회한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "folders",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_folder_id", sa.String(), sa.ForeignKey("folders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_folders_user_parent", "folders", ["user_id", "parent_folder_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_folders_user_parent_name "
        "ON folders (user_id, COALESCE(parent_folder_id, ''), name)"
    )

    op.add_column(
        "journal_entries",
        sa.Column(
            "folder_id",
            sa.String(),
            sa.ForeignKey("folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_journal_entries_folder_id", "journal_entries", ["folder_id"])

    op.add_column(
        "retro_summaries",
        sa.Column(
            "folder_id",
            sa.String(),
            sa.ForeignKey("folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_retro_summaries_folder_id", "retro_summaries", ["folder_id"])


def downgrade() -> None:
    op.drop_index("ix_retro_summaries_folder_id", table_name="retro_summaries")
    op.drop_column("retro_summaries", "folder_id")

    op.drop_index("ix_journal_entries_folder_id", table_name="journal_entries")
    op.drop_column("journal_entries", "folder_id")

    op.execute("DROP INDEX IF EXISTS uq_folders_user_parent_name")
    op.drop_index("ix_folders_user_parent", table_name="folders")
    op.drop_table("folders")
