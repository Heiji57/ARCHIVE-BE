from datetime import date, timedelta

from app.retrospective.domain.repositories.repository import IJournalEntryRepository
from app.shared.domain.utils.period import monday_of_week
from app.shared.domain.utils.period import today_in_tz
from app.todo.application.dtos.queries import GetTodoStatsQuery
from app.todo.domain.repositories.repository import (
    ITodoRepository,
    TagCount,
    TodoStatsRaw,
    WeeklyTrendDay,
)
from app.todo.presentation.responses.responses import (
    TagCountResponse,
    TodoStatsResponse,
    WeeklyTrendDayResponse,
)


def _iso_week_bounds(today: date) -> tuple[date, date]:
    monday = monday_of_week(today)
    return monday, monday + timedelta(days=6)


def _range_bounds(today: date, range_: str) -> tuple[date, date]:
    if range_ == "today":
        return today, today
    if range_ == "week":
        return _iso_week_bounds(today)
    # month
    first = today.replace(day=1)
    if today.month == 12:
        last = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        last = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    return first, last


def _fill_weekly_slots(
    trend_raw: list[WeeklyTrendDay], week_from: date, week_to: date
) -> list[WeeklyTrendDay]:
    by_date = {t.date_key: t.done_count for t in trend_raw}
    slots = []
    cursor = week_from
    while cursor <= week_to:
        dk = cursor.isoformat()
        slots.append(WeeklyTrendDay(date_key=dk, done_count=by_date.get(dk, 0)))
        cursor += timedelta(days=1)
    return slots


class GetTodoStatsUseCase:
    def __init__(
        self,
        todo_repo: ITodoRepository,
        entry_repo: IJournalEntryRepository,
    ) -> None:
        self._todo_repo = todo_repo
        self._entry_repo = entry_repo

    async def execute(self, query: GetTodoStatsQuery) -> TodoStatsResponse:
        today = today_in_tz(query.tz)

        range_from, range_to = _range_bounds(today, query.range)
        week_from, week_to = _iso_week_bounds(today)

        raw: TodoStatsRaw = await self._todo_repo.get_todo_stats(
            user_id=query.user_id,
            range_from=range_from.isoformat(),
            range_to=range_to.isoformat(),
            week_from=week_from.isoformat(),
            week_to=week_to.isoformat(),
            tz=query.tz,
        )
        retro_count = await self._entry_repo.count_all_by_user_id(query.user_id)

        completion_rate = (
            round(raw.done_count / raw.total * 100) if raw.total > 0 else 0
        )

        weekly_trend = _fill_weekly_slots(raw.weekly_trend, week_from, week_to)

        return TodoStatsResponse(
            range=query.range,
            total=raw.total,
            done_count=raw.done_count,
            in_progress_count=raw.in_progress_count,
            not_start_count=raw.not_start_count,
            completion_rate=completion_rate,
            weekly_trend=[WeeklyTrendDayResponse.from_domain(d) for d in weekly_trend],
            tag_distribution=[TagCountResponse.from_domain(t) for t in raw.tag_distribution],
            retro_count=retro_count,
        )
