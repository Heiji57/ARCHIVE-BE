"""시간만 바꿔 자정을 넘기면 date_key 도 start(없으면 end)의 로컬 날짜로 맞춰지는지.

move_to(날짜 이동 → 시간 평행이동)의 반대 방향. PATCH {startTime, endTime} 로
23:00 → 다음날 01:00 처럼 바꾸면 start_time 은 다음 날인데 date_key 는 그대로 남아
목록 날짜와 Google Calendar 이벤트 날짜가 어긋났다. 시리즈 base 는 date_key 가
시리즈 시작일이라 제외한다.
"""
from datetime import datetime, timezone

import pytest
from fastapi.exceptions import RequestValidationError

from app.todo.application.dtos.commands import UpdateTodoCommand
from app.todo.application.use_cases.update_todo import UpdateTodoUseCase
from app.todo.domain.models.todo import RecurrenceRule, Todo
from app.todo.domain.models.value_objects import TaskStatus

_NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)
_USER = "usr_1"


def _utc(*a: int) -> datetime:
    return datetime(*a, tzinfo=timezone.utc)


def _todo(**kw) -> Todo:
    base = dict(
        id="todo_1",
        user_id=_USER,
        title="t",
        status=TaskStatus.NOT_START,
        date_key="2026-09-16",
        # KST 09-16 23:00 ~ 23:30
        start_time=_utc(2026, 9, 16, 14, 0),
        end_time=_utc(2026, 9, 16, 14, 30),
        timezone="Asia/Seoul",
        created_at=_NOW,
        updated_at=_NOW,
    )
    base.update(kw)
    return Todo(**base)


class _Repo:
    def __init__(self, seed: list[Todo]) -> None:
        self.by_id = {t.id: t for t in seed}

    async def find_by_id(self, id: str, user_id: str) -> Todo | None:
        return self.by_id.get(id)

    async def find_series_base(self, series_id: str, user_id: str) -> Todo | None:
        t = self.by_id.get(series_id)
        return t if t and t.is_series_base else None

    async def save(self, todo: Todo) -> Todo:
        self.by_id[todo.id] = todo
        return todo

    async def upsert_exception(self, todo: Todo) -> Todo:
        self.by_id[todo.id] = todo
        return todo

    async def mark_for_push(self, todo_id: str, user_id: str) -> None:
        pass

    async def delete_all_exceptions(self, series_id: str, user_id: str) -> None:
        pass


async def _update(repo: _Repo, todo_id: str, **kw) -> Todo:
    out = await UpdateTodoUseCase(repo).execute(  # type: ignore[arg-type]
        UpdateTodoCommand(id=todo_id, user_id=_USER, **kw)
    )
    return out.todo


# ── 도메인 메서드 ─────────────────────────────────────────────────────────────


def test_align_uses_local_date_of_start() -> None:
    # 09-16 16:00Z == KST 09-17 01:00
    t = _todo(start_time=_utc(2026, 9, 16, 16, 0), end_time=None)
    t.align_date_to_time()
    assert t.date_key == "2026-09-17"


def test_align_falls_back_to_end() -> None:
    t = _todo(start_time=None, end_time=_utc(2026, 9, 17, 16, 0))
    t.align_date_to_time()
    assert t.date_key == "2026-09-18"


def test_align_noop_for_all_day_todo() -> None:
    t = _todo(start_time=None, end_time=None, timezone=None)
    t.align_date_to_time()
    assert t.date_key == "2026-09-16"


# ── UpdateTodoUseCase 경로 ────────────────────────────────────────────────────


async def test_time_change_crossing_midnight_moves_date_key() -> None:
    # KST 23:00 → 다음날 01:00~02:00
    repo = _Repo([_todo()])
    todo = await _update(
        repo, "todo_1", start_time=_utc(2026, 9, 16, 16, 0), end_time=_utc(2026, 9, 16, 17, 0)
    )
    assert todo.date_key == "2026-09-17"


async def test_time_change_within_same_day_keeps_date_key() -> None:
    repo = _Repo([_todo()])
    todo = await _update(repo, "todo_1", start_time=_utc(2026, 9, 16, 1, 0))
    assert todo.date_key == "2026-09-16"


async def test_explicit_date_key_in_same_request_wins() -> None:
    repo = _Repo([_todo()])
    todo = await _update(
        repo, "todo_1", date_key="2026-09-20", start_time=_utc(2026, 9, 16, 16, 0)
    )
    assert todo.date_key == "2026-09-20"


async def test_non_time_edit_does_not_realign() -> None:
    # 기존에 어긋난 row 라도 시간을 건드리지 않는 수정(제목 등)은 date_key 를 바꾸지 않는다
    repo = _Repo([_todo(date_key="2026-09-14")])
    todo = await _update(repo, "todo_1", title="변경")
    assert todo.date_key == "2026-09-14"


async def test_clearing_time_keeps_date_key() -> None:
    repo = _Repo([_todo()])
    todo = await _update(repo, "todo_1", start_time=None, end_time=None)
    assert todo.date_key == "2026-09-16"


async def test_due_date_key_validated_against_realigned_date() -> None:
    repo = _Repo([_todo()])
    with pytest.raises(RequestValidationError):
        await _update(
            repo, "todo_1", start_time=_utc(2026, 9, 16, 16, 0), due_date_key="2026-09-16"
        )


# ── 반복 시리즈 ───────────────────────────────────────────────────────────────


def _master() -> Todo:
    return _todo(
        id="todo_master",
        date_key="2026-09-07",
        start_time=_utc(2026, 9, 7, 14, 0),
        end_time=_utc(2026, 9, 7, 14, 30),
        recurrence_rule=RecurrenceRule(unit="week", interval=1),
    )


async def test_series_base_date_key_is_not_realigned() -> None:
    repo = _Repo([_master()])
    todo = await _update(
        repo, "todo_master", recurrence_scope="all", start_time=_utc(2026, 9, 7, 16, 0)
    )
    assert todo.date_key == "2026-09-07"


async def test_exception_row_is_realigned() -> None:
    # 가상 회차 "this" 수정으로 자정을 넘기면 예외 row 의 date_key 가 다음 날로
    repo = _Repo([_master()])
    todo = await _update(repo, "todo_master::2026-09-14", start_time=_utc(2026, 9, 14, 16, 0))
    assert todo.series_id == "todo_master"
    assert todo.date_key == "2026-09-15"
    assert todo.original_date_key == "2026-09-14"


async def test_timezone_only_change_realigns_date_key() -> None:
    # 09-16 14:00Z 는 KST 09-16 23:00 이지만 Pacific/Auckland(+12)로는 09-17 02:00
    repo = _Repo([_todo()])
    todo = await _update(repo, "todo_1", timezone="Pacific/Auckland")
    assert todo.start_time == _utc(2026, 9, 16, 14, 0)
    assert todo.date_key == "2026-09-17"
