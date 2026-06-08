"""Summary 생성 전략 — summary_type 별 데이터 소스 정책.

- WEEKLY  : EntriesOnlyStrategy   — 그 주 entry 들을 직접 사용
- MONTHLY : MonthlyHybridStrategy — 주마다 weekly summary 있으면 그것, 없으면 entries.
            weekly summary 가 있어도 갱신 이후 추가된 entry 가 있으면 보강 첨부 (방식 B).
- ANNUAL  : AnnualHybridStrategy  — 월마다 monthly summary 있으면 그것, 없으면 그 달의
            weekly summaries 로 보강. 둘 다 없으면 해당 월 스킵.

수동(`RequestSummaryUseCase`) / 자동(`dispatch_summaries_for_tz_task`) 모든 경로에
동일 정책 적용. path 일관성 보장.
"""
from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import SummaryStatus, SummaryType
from app.retrospective.infrastructure.ai.prompt_builder import (
    MonthSection,
    WeekSection,
    build_prompt_annual_hybrid,
    build_prompt_from_entries,
    build_prompt_monthly_hybrid,
)
from app.retrospective.infrastructure.persistence.repositories.journal_entry_repo import (
    JournalEntryRepository,
)
from app.retrospective.infrastructure.persistence.repositories.retro_summary_repo import (
    RetroSummaryRepository,
)
from app.shared.domain.utils.period import get_months_in_year, weeks_owned_by_month


class SummaryStrategy(ABC):
    @abstractmethod
    async def build_prompt(self, session: AsyncSession, summary: RetroSummary) -> str: ...


class EntriesOnlyStrategy(SummaryStrategy):
    async def build_prompt(self, session: AsyncSession, summary: RetroSummary) -> str:
        entry_repo = JournalEntryRepository(session)
        entries = await entry_repo.find_by_period(
            summary.user_id, summary.period_start, summary.period_end
        )
        return build_prompt_from_entries(summary.summary_type, entries)


class MonthlyHybridStrategy(SummaryStrategy):
    async def build_prompt(self, session: AsyncSession, summary: RetroSummary) -> str:
        entry_repo = JournalEntryRepository(session)
        summary_repo = RetroSummaryRepository(session)

        weeks = weeks_owned_by_month(summary.period_start.year, summary.period_start.month)
        sections: list[WeekSection] = []

        for idx, (w_start, w_end) in enumerate(weeks, start=1):
            weekly = await summary_repo.find_by_period(
                summary.user_id, SummaryType.WEEKLY, w_start
            )

            if (
                weekly is not None
                and weekly.status == SummaryStatus.COMPLETED
                and weekly.content is not None
            ):
                # 방식 B: weekly 갱신 이후 추가된 entry 자동 첨부
                weekly_ts = weekly.updated_at or weekly.created_at
                all_entries = await entry_repo.find_by_period(
                    summary.user_id, w_start, w_end
                )
                late = [e for e in all_entries if e.created_at > weekly_ts]
                sections.append(
                    WeekSection(
                        index=idx,
                        period_start=w_start,
                        period_end=w_end,
                        weekly_summary=weekly,
                        supplementary_entries=late,
                    )
                )
            else:
                week_entries = await entry_repo.find_by_period(
                    summary.user_id, w_start, w_end
                )
                sections.append(
                    WeekSection(
                        index=idx,
                        period_start=w_start,
                        period_end=w_end,
                        weekly_summary=None,
                        supplementary_entries=week_entries,
                    )
                )

        return build_prompt_monthly_hybrid(sections)


class AnnualHybridStrategy(SummaryStrategy):
    async def build_prompt(self, session: AsyncSession, summary: RetroSummary) -> str:
        summary_repo = RetroSummaryRepository(session)

        months = get_months_in_year(summary.period_start.year)
        sections: list[MonthSection] = []

        for idx, (m_start, m_end) in enumerate(months, start=1):
            monthly = await summary_repo.find_by_period(
                summary.user_id, SummaryType.MONTHLY, m_start
            )

            if (
                monthly is not None
                and monthly.status == SummaryStatus.COMPLETED
                and monthly.content is not None
            ):
                sections.append(
                    MonthSection(
                        month=idx,
                        monthly_summary=monthly,
                        weekly_summaries=[],
                    )
                )
            else:
                weeklies = await summary_repo.find_completed_in_range(
                    summary.user_id, SummaryType.WEEKLY, m_start, m_end
                )
                sections.append(
                    MonthSection(
                        month=idx,
                        monthly_summary=None,
                        weekly_summaries=weeklies,
                    )
                )

        return build_prompt_annual_hybrid(sections)


def get_strategy(summary_type: SummaryType) -> SummaryStrategy:
    if summary_type == SummaryType.WEEKLY:
        return EntriesOnlyStrategy()
    if summary_type == SummaryType.MONTHLY:
        return MonthlyHybridStrategy()
    if summary_type == SummaryType.ANNUAL:
        return AnnualHybridStrategy()
    raise ValueError(f"Unknown summary type: {summary_type}")
