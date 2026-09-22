"""`Todo.move_to` 가 시간 있는 todo 의 start/end 도 새 날짜로 평행이동하는지.

버그: move_to 가 date_key 만 바꿔서, FE 가 날짜만 옮기는(PATCH {dateKey}) 경우
start_time 이 옛 날짜에 남았다. Google Calendar push 는 시간 이벤트를 start/end 로만
만들기 때문에 캘린더 이벤트가 따라가지 않았다.
"""
from datetime import datetime, timezone

from app.todo.application.dtos.commands import UpdateTodoCommand
from app.todo.application.use_cases.update_todo import UpdateTodoUseCase
from app.todo.domain.models.todo import Todo
from app.todo.domain.models.value_objects import TaskStatus

_NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _todo(**kw) -> Todo:
    base = dict(
        id="todo_1",
        user_id="usr_1",
        title="t",
        status=TaskStatus.NOT_START,
        date_key="2026-09-14",
        created_at=_NOW,
        updated_at=_NOW,
        timezone="Asia/Seoul",
    )
    base.update(kw)
    return Todo(**base)


def _utc(*a: int) -> datetime:
    return datetime(*a, tzinfo=timezone.utc)


def test_moves_start_and_end_keeping_local_time_and_duration() -> None:
    # KST 2026-09-14 21:00 ~ 22:30
    t = _todo(start_time=_utc(2026, 9, 14, 12, 0), end_time=_utc(2026, 9, 14, 13, 30))
    t.move_to("2026-09-16")
    assert t.date_key == "2026-09-16"
    assert t.start_time == _utc(2026, 9, 16, 12, 0)
    assert t.end_time == _utc(2026, 9, 16, 13, 30)


def test_local_date_differs_from_utc_date() -> None:
    # KST 2026-09-15 08:00 == UTC 2026-09-14 23:00 — 기준은 로컬 날짜(09-15)
    t = _todo(date_key="2026-09-15", start_time=_utc(2026, 9, 14, 23, 0))
    t.move_to("2026-09-20")
    assert t.start_time == _utc(2026, 9, 19, 23, 0)


def test_multi_day_event_keeps_day_span() -> None:
    t = _todo(start_time=_utc(2026, 9, 14, 12, 0), end_time=_utc(2026, 9, 16, 12, 0))
    t.move_to("2026-09-20")
    assert t.start_time == _utc(2026, 9, 20, 12, 0)
    assert t.end_time == _utc(2026, 9, 22, 12, 0)


def test_end_only_is_shifted() -> None:
    t = _todo(end_time=_utc(2026, 9, 14, 12, 0))
    t.move_to("2026-09-15")
    assert t.start_time is None
    assert t.end_time == _utc(2026, 9, 15, 12, 0)


def test_all_day_todo_only_changes_date_key() -> None:
    t = _todo(timezone=None)
    t.move_to("2026-09-20")
    assert t.date_key == "2026-09-20"
    assert t.start_time is None and t.end_time is None


def test_dst_keeps_wall_clock_time() -> None:
    # America/New_York: 2026-11-01 DST 종료. 10-31 09:00 EDT(13:00Z) → 11-02 09:00 EST(14:00Z)
    t = _todo(
        date_key="2026-10-31",
        timezone="America/New_York",
        start_time=_utc(2026, 10, 31, 13, 0),
    )
    t.move_to("2026-11-02")
    assert t.start_time == _utc(2026, 11, 2, 14, 0)


def test_already_drifted_row_is_realigned_to_new_date() -> None:
    # 기존 버그로 date_key(09-16) 와 start(09-14) 가 어긋난 row
    t = _todo(date_key="2026-09-16", start_time=_utc(2026, 9, 14, 12, 0))
    t.move_to("2026-09-18")
    assert t.start_time == _utc(2026, 9, 18, 12, 0)


class _Repo:
    def __init__(self, todo: Todo) -> None:
        self.todo = todo

    async def find_by_id(self, id: str, user_id: str) -> Todo | None:
        return self.todo

    async def save(self, todo: Todo) -> Todo:
        return todo

    async def mark_for_push(self, todo_id: str, user_id: str) -> None:
        pass


async def test_update_with_date_key_only_shifts_time() -> None:
    repo = _Repo(_todo(start_time=_utc(2026, 9, 14, 12, 0), end_time=_utc(2026, 9, 14, 13, 0)))
    out = await UpdateTodoUseCase(repo).execute(  # type: ignore[arg-type]
        UpdateTodoCommand(id="todo_1", user_id="usr_1", date_key="2026-09-16")
    )
    assert out.todo.start_time == _utc(2026, 9, 16, 12, 0)
    assert out.todo.end_time == _utc(2026, 9, 16, 13, 0)


async def test_explicit_start_time_in_same_request_wins() -> None:
    repo = _Repo(_todo(start_time=_utc(2026, 9, 14, 12, 0)))
    out = await UpdateTodoUseCase(repo).execute(  # type: ignore[arg-type]
        UpdateTodoCommand(
            id="todo_1",
            user_id="usr_1",
            date_key="2026-09-16",
            start_time=_utc(2026, 9, 16, 1, 0),
        )
    )
    assert out.todo.start_time == _utc(2026, 9, 16, 1, 0)


async def test_timezone_change_in_same_request_uses_new_timezone() -> None:
    # 09-14 23:00Z 는 KST 로는 09-15 08:00. 새 tz(UTC) 기준이면 로컬 날짜 09-14 에서
    # 2일 이동 → 09-16 23:00Z. 옛 tz(KST) 기준이었다면 09-15 → 1일 이동 → 09-15 23:00Z.
    repo = _Repo(_todo(date_key="2026-09-14", start_time=_utc(2026, 9, 14, 23, 0)))
    out = await UpdateTodoUseCase(repo).execute(  # type: ignore[arg-type]
        UpdateTodoCommand(id="todo_1", user_id="usr_1", date_key="2026-09-16", timezone="UTC")
    )
    assert out.todo.timezone == "UTC"
    assert out.todo.start_time == _utc(2026, 9, 16, 23, 0)
