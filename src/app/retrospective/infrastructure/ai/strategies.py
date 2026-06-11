"""Summary 생성 전략 — summary_type 별 데이터 소스 정책.

- WEEKLY  : EntriesAndTodosStrategy — 그 주의 entry + (IN_PROGRESS or DONE) todo
- MONTHLY : MonthlyHybridStrategy   — 주마다 weekly summary 있으면 그것,
            없으면 entries. weekly 가 있어도 갱신 이후 추가된 entry 가 있으면 보강 (방식 B).
- ANNUAL  : AnnualHybridStrategy    — 월마다 monthly summary 있으면 그것, 없으면 weekly summaries.

모든 build_prompt 는 `locale` 과 `user_template` 을 인자로 받는다. 로케일은 AI 출력
언어 결정, user_template 은 출력 스타일 가이드(시스템 메시지에서 격리·제한됨).
"""
from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import SummaryStatus, SummaryType
from app.retrospective.infrastructure.ai.prompt_builder import (
    MonthSection,
    WeekSection,
    build_prompt_annual_hybrid,
    build_prompt_monthly_hybrid,
    build_prompt_weekly,
)
from app.retrospective.infrastructure.persistence.repositories.journal_entry_repo import (
    JournalEntryRepository,
)
from app.retrospective.infrastructure.persistence.repositories.retro_summary_repo import (
    RetroSummaryRepository,
)
from app.shared.domain.utils.period import get_months_in_year, weeks_owned_by_month
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.infrastructure.persistence.repositories.todo_repo import TodoRepository


class SummaryStrategy(ABC):
    @abstractmethod
    async def build_prompt(
        self,
        session: AsyncSession,
        summary: RetroSummary,
        locale: str,
        user_template: str,
    ) -> str: ...


class EntriesAndTodosStrategy(SummaryStrategy):
    """Weekly — entries + 그 주의 IN_PROGRESS / DONE todo 동시 사용."""

    async def build_prompt(
        self,
        session: AsyncSession,
        summary: RetroSummary,
        locale: str,
        user_template: str,
    ) -> str:
        entry_repo = JournalEntryRepository(session)
        todo_repo = TodoRepository(session)

        entries = await entry_repo.find_by_period(
            summary.user_id, summary.period_start, summary.period_end
        )

        # TodoRepository.find_by_date_range 는 YYYY-MM-DD 문자열을 받는다.
        todos_raw = await todo_repo.find_by_date_range(
            summary.user_id,
            summary.period_start.isoformat(),
            summary.period_end.isoformat(),
        )
        todos = [
            t for t in todos_raw
            if t.status in (TaskStatus.IN_PROGRESS, TaskStatus.DONE)
        ]

        return build_prompt_weekly(entries, todos, locale, user_template)


class MonthlyHybridStrategy(SummaryStrategy):
    async def build_prompt(
        self,
        session: AsyncSession,
        summary: RetroSummary,
        locale: str,
        user_template: str,
    ) -> str:
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

        return build_prompt_monthly_hybrid(sections, locale, user_template)


class AnnualHybridStrategy(SummaryStrategy):
    async def build_prompt(
        self,
        session: AsyncSession,
        summary: RetroSummary,
        locale: str,
        user_template: str,
    ) -> str:
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

        return build_prompt_annual_hybrid(sections, locale, user_template)


def get_strategy(summary_type: SummaryType) -> SummaryStrategy:
    if summary_type == SummaryType.WEEKLY:
        return EntriesAndTodosStrategy()
    if summary_type == SummaryType.MONTHLY:
        return MonthlyHybridStrategy()
    if summary_type == SummaryType.ANNUAL:
        return AnnualHybridStrategy()
    raise ValueError(f"Unknown summary type: {summary_type}")
