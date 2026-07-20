from datetime import date

from app.retrospective.application.dtos.summary_queries import (
    SummaryReadiness,
    SummaryReadinessQuery,
)
from app.retrospective.domain.exceptions.exceptions import (
    SummaryReadinessUnsupportedException,
)
from app.retrospective.domain.models.value_objects import SummaryType
from app.retrospective.domain.repositories.repository import IJournalEntryRepository
from app.retrospective.domain.utils.summary_period import calculate_summary_period

# 70% 미만이면 insufficient (FE 가 다이얼로그 띄움)
READINESS_THRESHOLD = 0.7


class GetSummaryReadinessUseCase:
    def __init__(self, entry_repo: IJournalEntryRepository) -> None:
        self._entry_repo = entry_repo

    async def execute(self, query: SummaryReadinessQuery) -> SummaryReadiness:
        if query.summary_type == SummaryType.WEEKLY:
            raise SummaryReadinessUnsupportedException()

        period_start, period_end = calculate_summary_period(
            query.summary_type, query.period_start
        )

        entries = await self._entry_repo.find_by_period(
            query.user_id, period_start, period_end
        )
        entry_count = len(entries)

        if query.summary_type == SummaryType.MONTHLY:
            expected = (period_end - period_start).days + 1
            covered = len({e.date_key for e in entries})
        else:  # ANNUAL
            expected = 12
            months_with_entries: set[int] = set()
            for e in entries:
                try:
                    d = date.fromisoformat(e.date_key)
                    months_with_entries.add(d.month)
                except ValueError:
                    continue
            covered = len(months_with_entries)

        ratio = covered / expected if expected > 0 else 0.0
        recommendation = "ok" if ratio >= READINESS_THRESHOLD else "insufficient"

        return SummaryReadiness(
            summary_type=query.summary_type,
            period_start=period_start,
            period_end=period_end,
            expected_units=expected,
            covered_units=covered,
            entry_count=entry_count,
            completeness_ratio=round(ratio, 4),
            recommendation=recommendation,
        )
