from datetime import date

from app.retrospective.application.dtos.queries import GetEntriesPageQuery
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import RetroType, SummaryType
from app.retrospective.domain.repositories.repository import (
    IJournalEntryRepository,
    IRetroSummaryRepository,
)
from app.retrospective.domain.utils.entry_ordering import merge_sorted_desc

# RetroType.YEARLY 는 push API/SummaryType 명명(annual)과 다르다 — 기존
# period_mapping 관례와 동일하게 여기서도 정규화한다.
_RETRO_TO_SUMMARY_TYPE = {
    RetroType.WEEKLY.value: SummaryType.WEEKLY,
    RetroType.MONTHLY.value: SummaryType.MONTHLY,
    RetroType.YEARLY.value: SummaryType.ANNUAL,
}


class GetEntriesPageUseCase:
    """회고록 목록 페이지 — daily 는 journal_entries, weekly/monthly/annual 은
    retro_summaries 에서 조회한다(소스 테이블이 다름). retro_type 미지정 시 두
    소스를 합쳐 최신순으로 정렬한 "전체" 뷰를 반환한다."""

    def __init__(
        self,
        entry_repo: IJournalEntryRepository,
        summary_repo: IRetroSummaryRepository,
    ) -> None:
        self._entry_repo = entry_repo
        self._summary_repo = summary_repo

    async def execute(
        self, query: GetEntriesPageQuery
    ) -> tuple[list[JournalEntry] | list[RetroSummary] | list[JournalEntry | RetroSummary], int]:
        from_d = date.fromisoformat(query.from_date) if query.from_date else None
        to_d = date.fromisoformat(query.to_date) if query.to_date else None

        if query.retro_type is None:
            return await self._execute_merged(query, from_d, to_d)

        if query.retro_type == RetroType.DAILY.value:
            return await self._entry_repo.find_page(
                query.user_id, query.retro_type, query.page, query.size, query.q, from_d, to_d
            )
        summary_type = _RETRO_TO_SUMMARY_TYPE[query.retro_type]
        return await self._summary_repo.find_page(
            query.user_id, summary_type, query.page, query.size, query.q, from_d, to_d
        )

    async def _execute_merged(
        self, query: GetEntriesPageQuery, from_d: date | None, to_d: date | None
    ) -> tuple[list[JournalEntry | RetroSummary], int]:
        # 전역 상위 (page*size) 개는 각 소스에서 상위 (page*size) 개씩만 가져오면
        # 항상 커버된다(어느 한쪽이 top-K 를 전부 차지해도 K개를 넘을 수 없으므로) —
        # 전체 이력을 다 훑지 않고도 정확한 페이지 슬라이스가 가능하다.
        fetch_size = query.page * query.size
        entries, entry_total = await self._entry_repo.find_page(
            query.user_id, None, 1, fetch_size, query.q, from_d, to_d
        )
        summaries, summary_total = await self._summary_repo.find_page(
            query.user_id, None, 1, fetch_size, query.q, from_d, to_d
        )
        merged = merge_sorted_desc(entries, summaries)
        start = (query.page - 1) * query.size
        page_items = merged[start : start + query.size]
        return page_items, entry_total + summary_total
