"""index optimization — drop redundant (prefix-covered) indexes + todos dedup unique

Revision ID: 027
Revises: 026
Create Date: 2026-07-07

목적:
  1. 중복 인덱스 6개 제거 — 각각 다른 인덱스의 leftmost prefix 에 완전히 커버되거나
     (btree 는 prefix 컬럼 조합 쿼리를 그대로 지원), 사용하는 쿼리가 코드에 없다.
     조회엔 무해하지만 INSERT/UPDATE 마다 유지 비용이 든다.
     - ix_journal_entries_user_id_retro_type   ⊂ ix_journal_entries_user_id_retro_type_date_key (026)
     - ix_journal_entries_user_id_date_key     ⊂ uq_journal_entries_user_date_retro_type
     - ix_retro_summaries_user_id              ⊂ uq_retro_summaries_user_type_period
     - ix_github_repositories_user_id          ⊂ uq_github_repositories_user_repo
     - ix_user_summary_templates_user_type     ⊂ uq_user_summary_templates_user_type_name
     - ix_users_timezone                       — timezone 으로 WHERE 하는 쿼리가 코드 전체에 없음
                                                 (dispatcher 는 auto_summary_* 로 필터, tz 는 SELECT 만)

  2. todos (user_id, google_event_id) partial UNIQUE 추가 — Google 원본 이벤트의
     todo 승격 dedup 이 지금까지 애플리케이션 로직(find_by_google_event_id)로만
     방어되어, 동시 sync race(주기 배치 + 즉시 task)에서 중복 todo 가 생길 수 있는
     구멍이 있었다. DB 제약으로 최종 방어 + 해당 lookup 의 인덱스 커버를 겸한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_journal_entries_user_id_retro_type", table_name="journal_entries")
    op.drop_index("ix_journal_entries_user_id_date_key", table_name="journal_entries")
    op.drop_index("ix_retro_summaries_user_id", table_name="retro_summaries")
    op.drop_index("ix_github_repositories_user_id", table_name="github_repositories")
    op.drop_index("ix_user_summary_templates_user_type", table_name="user_summary_templates")
    op.drop_index("ix_users_timezone", table_name="users")

    op.create_index(
        "uq_todos_user_google_event",
        "todos",
        ["user_id", "google_event_id"],
        unique=True,
        postgresql_where=sa.text("google_event_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_todos_user_google_event", table_name="todos")

    op.create_index("ix_users_timezone", "users", ["timezone"])
    op.create_index(
        "ix_user_summary_templates_user_type",
        "user_summary_templates",
        ["user_id", "summary_type"],
    )
    op.create_index("ix_github_repositories_user_id", "github_repositories", ["user_id"])
    op.create_index("ix_retro_summaries_user_id", "retro_summaries", ["user_id"])
    op.create_index(
        "ix_journal_entries_user_id_date_key", "journal_entries", ["user_id", "date_key"]
    )
    op.create_index(
        "ix_journal_entries_user_id_retro_type", "journal_entries", ["user_id", "retro_type"]
    )
