"""Summary 생성 전략 — summary_type 별 데이터 소스 정책.

- WEEKLY  : EntriesAndTodosStrategy — 그 주의 entry + (IN_PROGRESS or DONE) todo
- MONTHLY : MonthlyHybridStrategy   — 주마다 weekly summary 있으면 그것,
            없으면 entries. weekly 가 있어도 갱신 이후 추가된 entry 가 있으면 보강 (방식 B).
- ANNUAL  : AnnualHybridStrategy    — 월마다 monthly summary 있으면 그것, 없으면 weekly summaries.

모든 build_prompt 는 `user_template` 과 `locale` 을 인자로 받는다. 출력 언어는
prompt_builder 의 `_language_for_prompt`(콘텐츠 우선, locale 보조) 가 결정한다.

또한 모든 summary_type 은 해당 기간의 Google Calendar 이벤트(DB 저장본)를 읽어
프롬프트에 read-only 컨텍스트로 주입한다 (`_fetch_calendar_inputs`). worker 에서
Google API 동기 호출은 하지 않는다 — 최신성은 GET /todos 온디맨드 sync 가 담당.
"""
from abc import ABC, abstractmethod
from datetime import timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.google_calendar.domain.models.calendar_event import CalendarEvent
from app.google_calendar.infrastructure.persistence.repositories.calendar_event_repo import (
    CalendarEventRepository,
)
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import SummaryStatus, SummaryType
from app.retrospective.infrastructure.ai.prompt_builder import (
    CalendarEventInput,
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


def _event_time_range(event: CalendarEvent) -> str | None:
    """이벤트 시간 범위를 이벤트 자체 tz 기준 "HH:MM–HH:MM" 로. 종일/시간없음은 None."""
    if event.all_day or event.start_at is None:
        return None
    tz = ZoneInfo(event.timezone) if event.timezone else timezone.utc
    out = event.start_at.astimezone(tz).strftime("%H:%M")
    if event.end_at is not None:
        out += "–" + event.end_at.astimezone(tz).strftime("%H:%M")
    return out


async def _fetch_calendar_inputs(
    session: AsyncSession, summary: RetroSummary
) -> list[CalendarEventInput]:
    """요약 기간의 저장된 캘린더 이벤트를 프롬프트 입력으로 매핑.

    백그라운드 worker 에서 Google API 동기 호출(지연/실패 위험)을 피하기 위해
    DB 에 저장된 이벤트만 읽는다 — GET /todos 온디맨드 sync 가 최신성을 유지.
    """
    repo = CalendarEventRepository(session)
    events = await repo.find_by_date_range(
        summary.user_id,
        summary.period_start.isoformat(),
        summary.period_end.isoformat(),
    )
    return [
        CalendarEventInput(
            date_key=e.date_key,
            title=e.title,
            time_range=_event_time_range(e),
            location=e.location,
        )
        for e in events
    ]


def _usable(summary: RetroSummary | None) -> bool:
    """상위 요약의 입력으로 쓸 수 있는 하위 요약인가 — 빈 기간 안내 문구는 입력이 아니다."""
    return (
        summary is not None
        and summary.status == SummaryStatus.COMPLETED
        and summary.content is not None
        and not summary.is_empty
    )


class SummaryStrategy(ABC):
    @abstractmethod
    async def build_prompt(
        self,
        session: AsyncSession,
        summary: RetroSummary,
        user_template: str,
        locale: str | None = None,
    ) -> str | None:
        """요약할 소스(회고·할일·하위 요약)가 하나도 없으면 None — 호출자는 AI 를 건너뛴다.

        캘린더 일정만 있는 기간도 None 이다. 일정 목록만으로는 회고 요약이 되지 않고
        LLM 이 없는 인사이트를 지어낼 위험이 있다.
        """
        ...


class EntriesAndTodosStrategy(SummaryStrategy):
    """Weekly — entries + 그 주의 IN_PROGRESS / DONE todo 동시 사용."""

    async def build_prompt(
        self,
        session: AsyncSession,
        summary: RetroSummary,
        user_template: str,
        locale: str | None = None,
    ) -> str | None:
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
        if not entries and not todos:
            return None

        calendar_events = await _fetch_calendar_inputs(session, summary)

        return build_prompt_weekly(
            entries, todos, user_template, locale, calendar_events
        )


class MonthlyHybridStrategy(SummaryStrategy):
    async def build_prompt(
        self,
        session: AsyncSession,
        summary: RetroSummary,
        user_template: str,
        locale: str | None = None,
    ) -> str | None:
        entry_repo = JournalEntryRepository(session)
        summary_repo = RetroSummaryRepository(session)

        weeks = weeks_owned_by_month(summary.period_start.year, summary.period_start.month)
        sections: list[WeekSection] = []

        for idx, (w_start, w_end) in enumerate(weeks, start=1):
            weekly = await summary_repo.find_by_period(
                summary.user_id, SummaryType.WEEKLY, w_start
            )

            # 빈 주간 요약은 없는 것으로 본다 — 그 뒤 과거 날짜로 쓴 회고가 아래 else 에서
            # 원문으로 들어간다.
            if weekly is not None and _usable(weekly):
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

        if all(s.weekly_summary is None and not s.supplementary_entries for s in sections):
            return None

        calendar_events = await _fetch_calendar_inputs(session, summary)

        return build_prompt_monthly_hybrid(
            sections, user_template, locale, calendar_events
        )


class AnnualHybridStrategy(SummaryStrategy):
    async def build_prompt(
        self,
        session: AsyncSession,
        summary: RetroSummary,
        user_template: str,
        locale: str | None = None,
    ) -> str | None:
        summary_repo = RetroSummaryRepository(session)

        months = get_months_in_year(summary.period_start.year)
        sections: list[MonthSection] = []

        for idx, (m_start, m_end) in enumerate(months, start=1):
            monthly = await summary_repo.find_by_period(
                summary.user_id, SummaryType.MONTHLY, m_start
            )

            if monthly is not None and _usable(monthly):
                sections.append(
                    MonthSection(
                        month=idx,
                        monthly_summary=monthly,
                        weekly_summaries=[],
                    )
                )
            else:
                weeklies = [
                    w
                    for w in await summary_repo.find_completed_in_range(
                        summary.user_id, SummaryType.WEEKLY, m_start, m_end
                    )
                    if _usable(w)
                ]
                sections.append(
                    MonthSection(
                        month=idx,
                        monthly_summary=None,
                        weekly_summaries=weeklies,
                    )
                )

        if all(s.monthly_summary is None and not s.weekly_summaries for s in sections):
            return None

        calendar_events = await _fetch_calendar_inputs(session, summary)

        return build_prompt_annual_hybrid(
            sections, user_template, locale, calendar_events
        )


def get_strategy(summary_type: SummaryType) -> SummaryStrategy:
    if summary_type == SummaryType.WEEKLY:
        return EntriesAndTodosStrategy()
    if summary_type == SummaryType.MONTHLY:
        return MonthlyHybridStrategy()
    if summary_type == SummaryType.ANNUAL:
        return AnnualHybridStrategy()
    raise ValueError(f"Unknown summary type: {summary_type}")
