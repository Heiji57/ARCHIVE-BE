from app.retrospective.application.dtos.queries import GetEntriesPageQuery
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import RetroType, SummaryType
from app.retrospective.domain.repositories.repository import (
    IJournalEntryRepository,
    IRetroSummaryRepository,
)

# RetroType.YEARLY 는 push API/SummaryType 명명(annual)과 다르다 — 기존
# period_mapping 관례와 동일하게 여기서도 정규화한다.
_RETRO_TO_SUMMARY_TYPE = {
    RetroType.WEEKLY.value: SummaryType.WEEKLY,
    RetroType.MONTHLY.value: SummaryType.MONTHLY,
    RetroType.YEARLY.value: SummaryType.ANNUAL,
}


class GetEntriesPageUseCase:
    """회고록 목록 페이지 — daily 는 journal_entries, weekly/monthly/annual 은
    retro_summaries 에서 조회한다(소스 테이블이 다름 — retro_type 필수)."""

    def __init__(
        self,
        entry_repo: IJournalEntryRepository,
        summary_repo: IRetroSummaryRepository,
    ) -> None:
        self._entry_repo = entry_repo
        self._summary_repo = summary_repo

    async def execute(
        self, query: GetEntriesPageQuery
    ) -> tuple[list[JournalEntry] | list[RetroSummary], int]:
        if query.retro_type == RetroType.DAILY.value:
            return await self._entry_repo.find_page(
                query.user_id, query.retro_type, query.page, query.size, query.q
            )
        summary_type = _RETRO_TO_SUMMARY_TYPE[query.retro_type]
        return await self._summary_repo.find_page(
            query.user_id, summary_type, query.page, query.size, query.q
        )
