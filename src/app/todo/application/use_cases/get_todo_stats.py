from datetime import date, timedelta

from app.retrospective.domain.repositories.repository import IJournalEntryRepository
from app.shared.domain.utils.period import monday_of_week
from app.shared.domain.utils.period import today_in_tz
from app.todo.application.dtos.queries import GetTodoStatsQuery
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.domain.repositories.repository import (
    ITodoRepository,
    TagCount,
    TodoStatsRaw,
    WeeklyTrendDay,
)
from app.todo.domain.utils.recurrence import generate_slots_from
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

        # ── 반복 Todo 가상 인스턴스 집계 ────────────────────────────────────────
        # DB 쿼리는 exception row(series_id IS NOT NULL)만 집계하고,
        # DB에 row가 없는 가상 인스턴스(미수정 반복 발생)는 누락된다.
        # get_todos_by_date 와 동일한 패턴으로 가상 슬롯을 보정한다.
        virtual_total = virtual_done = virtual_in_progress = virtual_not_start = 0

        masters = await self._todo_repo.find_masters_overlapping(
            query.user_id, range_from.isoformat(), range_to.isoformat()
        )
        if masters:
            series_ids = [m.id for m in masters]
            exceptions = await self._todo_repo.find_exceptions_batch(
                query.user_id, series_ids, range_from.isoformat(), range_to.isoformat()
            )
            # (series_id, original_date_key) 로 점유된 슬롯 — cancelled 포함하여
            # 해당 슬롯을 가상 인스턴스로 중복 집계하지 않는다.
            covered: set[tuple[str, str]] = {
                (e.series_id, e.original_date_key)  # type: ignore[index]
                for e in exceptions
            }

            for master in masters:
                slots = generate_slots_from(
                    master.recurrence_rule,  # type: ignore[arg-type]
                    master.date_key,
                    range_from.isoformat(),
                    range_to.isoformat(),
                )
                for slot in slots:
                    if (master.id, slot) in covered:
                        continue  # exception row 가 이미 DB 쿼리에서 집계됨
                    virtual_total += 1
                    if master.status == TaskStatus.DONE:
                        virtual_done += 1
                    elif master.status == TaskStatus.IN_PROGRESS:
                        virtual_in_progress += 1
                    else:
                        virtual_not_start += 1

        total = raw.total + virtual_total
        done_count = raw.done_count + virtual_done
        in_progress_count = raw.in_progress_count + virtual_in_progress
        not_start_count = raw.not_start_count + virtual_not_start

        completion_rate = (
            round(done_count / total * 100) if total > 0 else 0
        )

        # weekly_trend·tag_distribution은 DB row(exception) 기준만 집계한다.
        # virtual instance는 master의 completed_at이 슬롯별 날짜와 무관하여
        # 날짜별 추세·태그 분포에 의미있는 값을 낼 수 없다.
        weekly_trend = _fill_weekly_slots(raw.weekly_trend, week_from, week_to)

        return TodoStatsResponse(
            range=query.range,
            total=total,
            done_count=done_count,
            in_progress_count=in_progress_count,
            not_start_count=not_start_count,
            completion_rate=completion_rate,
            weekly_trend=[WeeklyTrendDayResponse.from_domain(d) for d in weekly_trend],
            tag_distribution=[TagCountResponse.from_domain(t) for t in raw.tag_distribution],
            retro_count=retro_count,
        )
