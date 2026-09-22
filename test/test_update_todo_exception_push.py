"""반복 시리즈 예외 row("이 일정만" 수정)가 Google Calendar instance 로 push 되는지.

버그: 가상 회차 실체화(_materialize_and_update)에는 mark_for_push 가 없었고, 이미
실체화된 예외 row 수정(_update_real)은 예외 row 자신의 calendar_push_status(항상
NULL)를 봐서 push 가 한 번도 예약되지 않았다. 또 종일 시리즈는 original_start_time
이 없어 워커가 instance PATCH 대신 별도 이벤트를 만들었다(중복).
"""
from datetime import datetime, timezone

from app.google_calendar.application.services.calendar_push_service import (
    CalendarPushService,
)
from app.todo.application.dtos.commands import UpdateTodoCommand
from app.todo.application.use_cases.update_todo import UpdateTodoUseCase
from app.todo.domain.models.todo import RecurrenceRule, Todo
from app.todo.domain.models.value_objects import TaskStatus

_NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)
_USER = "usr_1"


def _master(**kw) -> Todo:
    base = dict(
        id="todo_master",
        user_id=_USER,
        title="회의",
        status=TaskStatus.NOT_START,
        date_key="2026-09-07",
        start_time=datetime(2026, 9, 7, 13, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 7, 14, 0, tzinfo=timezone.utc),
        timezone="Asia/Seoul",
        created_at=_NOW,
        updated_at=_NOW,
        recurrence_rule=RecurrenceRule(unit="week", interval=1),
        calendar_push_status="synced",
        google_event_id="gmaster",
    )
    base.update(kw)
    return Todo(**base)


def _exception(**kw) -> Todo:
    base = dict(
        id="todo_exc",
        user_id=_USER,
        title="회의",
        status=TaskStatus.NOT_START,
        date_key="2026-09-14",
        start_time=datetime(2026, 9, 14, 13, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 14, 14, 0, tzinfo=timezone.utc),
        timezone="Asia/Seoul",
        created_at=_NOW,
        updated_at=_NOW,
        series_id="todo_master",
        original_date_key="2026-09-14",
        original_start_time=datetime(2026, 9, 14, 13, 0, tzinfo=timezone.utc),
        master_google_event_id=None,
    )
    base.update(kw)
    return Todo(**base)


class FakeRepo:
    def __init__(self, seed: list[Todo]) -> None:
        self.by_id = {t.id: t for t in seed}
        self.marked: list[str] = []

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
        self.marked.append(todo_id)


async def _update(repo: FakeRepo, todo_id: str, **kw) -> Todo:
    out = await UpdateTodoUseCase(repo).execute(  # type: ignore[arg-type]
        UpdateTodoCommand(id=todo_id, user_id=_USER, **kw)
    )
    return out.todo


# ── 가상 회차 실체화 ("this") ─────────────────────────────────────────────────


async def test_materialize_on_linked_series_marks_exception_for_push() -> None:
    repo = FakeRepo([_master()])
    todo = await _update(repo, "todo_master::2026-09-14", title="변경")
    assert repo.marked == [todo.id]
    assert todo.calendar_push_status == "pending"
    assert todo.master_google_event_id == "gmaster"


async def test_materialize_on_unlinked_series_does_not_push() -> None:
    repo = FakeRepo([_master(calendar_push_status=None, google_event_id=None)])
    todo = await _update(repo, "todo_master::2026-09-14", title="변경")
    assert repo.marked == []
    assert todo.calendar_push_status is None


async def test_materialize_on_series_pending_delete_does_not_push() -> None:
    repo = FakeRepo([_master(calendar_push_status="pending_delete", push_intent="delete")])
    await _update(repo, "todo_master::2026-09-14", title="변경")
    assert repo.marked == []


async def test_materialize_on_series_not_yet_pushed_does_not_push() -> None:
    # master push 대기(gid 없음) → instance ID 를 만들 수 없어 제외
    repo = FakeRepo(
        [_master(calendar_push_status="pending", push_intent="push", google_event_id=None)]
    )
    await _update(repo, "todo_master::2026-09-14", title="변경")
    assert repo.marked == []


# ── 이미 실체화된 예외 row 수정 ───────────────────────────────────────────────


async def test_existing_exception_edit_pushes_and_refreshes_master_gid() -> None:
    # 예외 row 생성 뒤 master 가 push 된 경우 — 스냅샷 NULL 을 master gid 로 갱신
    repo = FakeRepo([_master(), _exception()])
    todo = await _update(repo, "todo_exc", date_key="2026-09-15")
    assert repo.marked == ["todo_exc"]
    assert todo.calendar_push_status == "pending"
    assert todo.master_google_event_id == "gmaster"
    assert repo.by_id["todo_exc"].master_google_event_id == "gmaster"


async def test_existing_exception_edit_on_unlinked_series_does_not_push() -> None:
    repo = FakeRepo([_master(calendar_push_status=None, google_event_id=None), _exception()])
    todo = await _update(repo, "todo_exc", title="변경")
    assert repo.marked == []
    assert todo.calendar_push_status is None


async def test_plain_todo_push_rule_unchanged() -> None:
    plain = _master(id="todo_plain", recurrence_rule=None)
    repo = FakeRepo([plain])
    await _update(repo, "todo_plain", title="변경")
    assert repo.marked == ["todo_plain"]


# ── 워커 push 경로: 종일 예외도 instance PATCH ────────────────────────────────


class FakeApi:
    def __init__(self) -> None:
        self.patched: list[str] = []
        self.created = 0

    async def patch_instance(self, access_token, instance_id, ev):
        self.patched.append(instance_id)
        return instance_id

    async def create_event(self, access_token, ev):
        self.created += 1
        return "gnew"

    async def find_event_id_by_archive_todo_id(self, access_token, archive_todo_id):
        return None


async def test_all_day_exception_uses_instance_patch() -> None:
    api = FakeApi()
    exc = _exception(
        start_time=None,
        end_time=None,
        original_start_time=None,
        master_google_event_id="gmaster",
    )
    outcome = await CalendarPushService(api).push_one("tok", exc)  # type: ignore[arg-type]
    assert api.patched == ["gmaster_20260914"]
    assert api.created == 0
    assert outcome.result_gid == "gmaster_20260914"


async def test_timed_exception_uses_utc_instance_id() -> None:
    api = FakeApi()
    exc = _exception(master_google_event_id="gmaster")
    await CalendarPushService(api).push_one("tok", exc)  # type: ignore[arg-type]
    assert api.patched == ["gmaster_20260914T130000Z"]
