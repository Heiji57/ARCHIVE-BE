"""AI 포트 → GitHub 커밋 조회. 연결이 없거나 GitHub 가 실패해도 추천은 계속돼야 한다."""

from datetime import date
from typing import Any

import structlog

from app.github.application.use_cases.get_commits_by_date import GetCommitsByDateUseCase
from app.shared.domain.exceptions.base import BaseAppException

_log = structlog.get_logger(__name__)


class CommitAdapter:
    def __init__(self, commits_uc: GetCommitsByDateUseCase) -> None:
        self._uc = commits_uc

    async def messages_on(self, user_id: str, day: date) -> list[str]:
        try:
            result = await self._uc.execute(user_id, day, day)
        except BaseAppException as e:
            # 미연결(GITHUB_CONNECTION_NOT_FOUND)·토큰 만료·GitHub 장애 — 커밋 추천만 빠진다.
            _log.info("ai.commits_unavailable", user_id=user_id, code=e.code)
            return []
        return [c.message for c in result.commits]

    async def list_range(self, user_id: str, from_day: date, to_day: date) -> list[dict[str, Any]]:
        try:
            result = await self._uc.execute(user_id, from_day, to_day)
        except BaseAppException as e:
            _log.info("ai.commits_unavailable", user_id=user_id, code=e.code)
            return []
        return [
            {"date": c.date_key, "repository": c.full_name, "message": c.message}
            for c in result.commits
        ]
