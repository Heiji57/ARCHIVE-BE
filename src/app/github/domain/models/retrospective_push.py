"""GitHub 에 push 된 회고록 기록 — (user_id, period_type, period_key) 단위.

JournalEntry / RetroSummary 어느 쪽이 push 되었든 동일 period 면 같은 레코드를 공유.
이는 GitHub 측 파일 경로 (`{period_folder}/{period_key}.md`) 가 1:1 매핑되기 때문.
"""
from dataclasses import dataclass
from datetime import datetime

from app.shared.domain.models.base import BaseEntity


@dataclass(kw_only=True)
class RetrospectivePush(BaseEntity):
    user_id: str
    period_type: str               # 'daily' | 'weekly' | 'monthly' | 'annual'
    period_key: str                # 'YYYY-MM-DD' | 'YYYY-MM-WN' | 'YYYY-MM' | 'YYYY'
    repository_id: str             # 백엔드 github_repositories.id (unlink 후 무효)
    repository_full_name: str      # 'owner/name' (denormalized — repo unlink 후에도 표시 가능)
    path: str
    commit_sha: str
    html_url: str
    pushed_at: datetime
