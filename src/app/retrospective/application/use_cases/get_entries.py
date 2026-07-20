from datetime import date, timedelta

from app.retrospective.application.dtos.queries import GetEntriesQuery
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.repositories.repository import IJournalEntryRepository

# retroType 만 오고 from/to 가 없을 때(초기 하이드레이션) 적용하는 기본 조회 범위 —
# 과거엔 무제한 전체 이력을 반환했음(사용자가 오래 쓸수록 payload 무한 증가).
DEFAULT_HYDRATION_DAYS = 30


class GetEntriesUseCase:
    def __init__(self, entry_repo: IJournalEntryRepository) -> None:
        self._entry_repo = entry_repo

    async def execute(self, query: GetEntriesQuery) -> list[JournalEntry]:
        if query.retro_type:
            since = date.today() - timedelta(days=DEFAULT_HYDRATION_DAYS)
            return await self._entry_repo.find_by_retro_type(
                query.user_id, query.retro_type, since
            )

        if query.from_date and query.to_date:
            return await self._entry_repo.find_by_period(
                query.user_id,
                date.fromisoformat(query.from_date),
                date.fromisoformat(query.to_date),
            )

        return []
