"""할 일 묶음 수정(`POST /todos/batch`)과 기간 밖 조회(`GET /todos?overdue|due|calendarPushStatus`).

- 묶음 수정은 건별 규칙을 단건 수정과 공유하고, 하나라도 실패하면 건별 실패 이유를 모아
  TODO_BATCH_FAILED 로 던진다(요청 트랜잭션이 통째로 롤백된다).
- `previous` 는 변경 전 값이라 FE 되돌리기가 그대로 다시 묶음 수정에 넣을 수 있다.
- 조회 모드는 하나만 — 섞으면 TODO_QUERY_CONFLICT.
"""
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.todo.application.dtos.queries import GetTodosFilteredQuery
from app.todo.application.use_cases.batch_update_todos import BatchUpdateTodosUseCase
from app.todo.application.use_cases.get_todos_filtered import GetTodosFilteredUseCase
from app.todo.application.use_cases.update_todo import UpdateTodoUseCase
from app.todo.domain.exceptions.exceptions import (
    TodoBatchFailedException,
    TodoQueryConflictException,
)
from app.todo.domain.models.todo import RecurrenceRule, Todo
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.presentation.requests.requests import TodoBatchRequest
from app.todo.presentation.router import _to_update_command, get_todos


class FakeTodoRepo:
    def __init__(self, seed: list[Todo]) -> None:
        self.by_id: dict[str, Todo] = {t.id: t for t in seed}
        self.filtered_calls: list[dict] = []

    async def save(self, todo: Todo) -> Todo:
        self.by_id[todo.id] = todo
        return todo

    async def find_by_id(self, id: str, user_id: str) -> Todo | None:
        t = self.by_id.get(id)
        return t if t and t.user_id == user_id else None

    async def find_series_base(self, series_id: str, user_id: str) -> Todo | None:
        t = self.by_id.get(series_id)
        return t if t and t.user_id == user_id and t.is_series_base else None

    async def upsert_exception(self, todo: Todo) -> Todo:
        self.by_id[todo.id] = todo
        return todo

    async def mark_for_push(self, todo_id: str, user_id: str) -> None:
        pass

    async def find_filtered(self, user_id: str, **kwargs) -> list[Todo]:
        self.filtered_calls.append({"user_id": user_id, **kwargs})
        return []


def _todo(id: str, date_key: str = "2026-11-10", **kw) -> Todo:
    return Todo(
        id=id,
        user_id="usr_1",
        title=kw.pop("title", id),
        status=kw.pop("status", TaskStatus.NOT_START),
        date_key=date_key,
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
        **kw,
    )


def _batch_uc(repo: FakeTodoRepo) -> BatchUpdateTodosUseCase:
    return BatchUpdateTodosUseCase(repo, UpdateTodoUseCase(repo))  # type: ignore[arg-type]


def _commands(ops: list[dict]):
    req = TodoBatchRequest.model_validate({"operations": ops})
    return [_to_update_command(op.id, "usr_1", op.patch) for op in req.operations]


# ── 묶음 수정 ────────────────────────────────────────────────────────────────


async def test_batch_updates_all_and_returns_previous():
    repo = FakeTodoRepo([_todo("t1"), _todo("t2", title="old")])
    result = await _batch_uc(repo).execute(
        "usr_1",
        _commands([
            {"id": "t1", "patch": {"date_key": "2026-11-12", "status": "done"}},
            {"id": "t2", "patch": {"title": "new"}},
        ]),
    )

    assert [o.todo.id for o in result.outcomes] == ["t1", "t2"]
    assert repo.by_id["t1"].date_key == "2026-11-12"
    assert repo.by_id["t1"].status == TaskStatus.DONE
    assert repo.by_id["t2"].title == "new"
    # previous 는 변경 전 값(제자리 수정에 오염되지 않은 복사본)
    assert result.previous[0].date_key == "2026-11-10"
    assert result.previous[0].status == TaskStatus.NOT_START
    assert result.previous[1].title == "old"


async def test_batch_collects_all_failures():
    repo = FakeTodoRepo([_todo("t1")])
    with pytest.raises(TodoBatchFailedException) as ei:
        await _batch_uc(repo).execute(
            "usr_1",
            _commands([
                {"id": "missing", "patch": {"title": "x"}},
                {"id": "t1", "patch": {"title": "ok"}},
                {"id": "t1-due", "patch": {"title": "x"}},
            ]),
        )
    assert ei.value.details == [
        {"id": "missing", "code": "TODO_NOT_FOUND"},
        {"id": "t1-due", "code": "TODO_NOT_FOUND"},
    ]


async def test_batch_reports_use_case_validation_error():
    repo = FakeTodoRepo([_todo("t1", date_key="2026-11-10")])
    with pytest.raises(TodoBatchFailedException) as ei:
        # due_date_key < date_key — 요청 단계가 아니라 use case 에서 걸리는 검증
        await _batch_uc(repo).execute(
            "usr_1", _commands([{"id": "t1", "patch": {"due_date_key": "2026-11-01"}}])
        )
    assert ei.value.details == [{"id": "t1", "code": "VALIDATION_ERROR"}]


async def test_batch_previous_for_virtual_instance_is_the_slot():
    master = _todo(
        "base", date_key="2026-11-01", recurrence_rule=RecurrenceRule(unit="day", interval=1)
    )
    repo = FakeTodoRepo([master])
    virtual_id = "base::2026-11-05"
    result = await _batch_uc(repo).execute(
        "usr_1", _commands([{"id": virtual_id, "patch": {"title": "회차만"}}])
    )
    assert result.previous[0].id == virtual_id
    assert result.previous[0].date_key == "2026-11-05"
    assert result.previous[0].title == "base"
    assert result.outcomes[0].todo.title == "회차만"


@pytest.mark.parametrize(
    "ops",
    [
        [],
        [{"id": f"t{i}", "patch": {}} for i in range(101)],
        [{"id": "t1", "patch": {}}, {"id": "t1", "patch": {"title": "x"}}],
    ],
    ids=["empty", "over-100", "duplicate"],
)
def test_batch_request_rejects_invalid_operations(ops):
    with pytest.raises(ValidationError):
        TodoBatchRequest.model_validate({"operations": ops})


def test_batch_request_accepts_100():
    req = TodoBatchRequest.model_validate(
        {"operations": [{"id": f"t{i}", "patch": {"status": "done"}} for i in range(100)]}
    )
    assert len(req.operations) == 100


# ── 기간 밖 조회 ─────────────────────────────────────────────────────────────


async def test_filtered_overdue_uses_today_in_user_tz(monkeypatch):
    from datetime import date

    import app.todo.application.use_cases.get_todos_filtered as mod

    seen: list[str] = []

    def fake_today(tz: str) -> date:
        seen.append(tz)
        return date(2026, 11, 16)

    monkeypatch.setattr(mod, "today_in_tz", fake_today)
    repo = FakeTodoRepo([])
    await GetTodosFilteredUseCase(repo).execute(  # type: ignore[arg-type]
        GetTodosFilteredQuery(user_id="usr_1", tz="Asia/Seoul", overdue=True, page=2, size=10)
    )
    assert seen == ["Asia/Seoul"]
    assert repo.filtered_calls == [{
        "user_id": "usr_1",
        "overdue_before": "2026-11-16",
        "due_from": None,
        "due_to": None,
        "push_status": None,
        "calendar_ids": None,
        "include_default_calendar": False,
        "offset": 10,
        "limit": 10,
    }]


async def test_filtered_due_and_push_status_do_not_compute_today():
    repo = FakeTodoRepo([])
    await GetTodosFilteredUseCase(repo).execute(  # type: ignore[arg-type]
        GetTodosFilteredQuery(
            user_id="usr_1", tz="UTC", due_from="2026-11-16", due_to="2026-11-22"
        )
    )
    await GetTodosFilteredUseCase(repo).execute(  # type: ignore[arg-type]
        GetTodosFilteredQuery(user_id="usr_1", tz="UTC", push_status="failed")
    )
    assert repo.filtered_calls[0]["overdue_before"] is None
    assert (repo.filtered_calls[0]["due_from"], repo.filtered_calls[0]["due_to"]) == (
        "2026-11-16",
        "2026-11-22",
    )
    assert repo.filtered_calls[1]["push_status"] == "failed"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"date_key": "2026-11-16", "overdue": True},
        {"from_date": "2026-11-01", "to_date": "2026-11-30", "due": "2026-11-01..2026-11-07"},
        {"overdue": True, "calendar_push_status": "failed"},
    ],
)
async def test_get_todos_rejects_mixed_modes(kwargs):
    base = {
        "date_key": None,
        "from_date": None,
        "to_date": None,
        "overdue": False,
        "due": None,
        "calendar_push_status": None,
        "page": 1,
        "size": 50,
        "calendar_ids": None,
    }
    with pytest.raises(TodoQueryConflictException):
        await get_todos(
            by_date_uc=None,
            by_range_uc=None,
            filtered_uc=None,
            calendar_uc=None,
            user_repo=None,
            calendar_repo=None,
            current_user=SimpleNamespace(id="usr_1"),
            **{**base, **kwargs},
        )


async def test_batch_previous_is_taken_before_any_operation():
    """앞 건이 시리즈 전체를 바꿔도 뒤 건의 previous 는 묶음 전 값이어야 한다."""
    master = _todo(
        "base", date_key="2026-11-01", recurrence_rule=RecurrenceRule(unit="day", interval=1)
    )
    repo = FakeTodoRepo([master])

    async def _noop(*a, **kw):
        return None

    repo.delete_all_exceptions = _noop  # type: ignore[attr-defined]
    result = await _batch_uc(repo).execute(
        "usr_1",
        _commands([
            {"id": "base::2026-11-05", "patch": {"title": "전체", "recurrence_scope": "all"}},
            {"id": "base::2026-11-06", "patch": {"status": "done"}},
        ]),
    )
    assert [p.title for p in result.previous] == ["base", "base"]
