"""
반복 시리즈를 recurrence_scope="following" 으로 삭제할 때, GCal 에 연동된 시리즈라면
truncate 된 RRULE(UNTIL) 이 Google 에도 반영되도록 재푸시가 예약되는지 검증한다.

버그: 기존엔 로컬 DB 의 recurrence_rule.until 은 truncate 되고 이후 exception row 는
삭제되지만, 그 사실이 Google Calendar 에 전혀 반영되지 않아(재푸시 트리거 없음)
캘린더 상에는 삭제된 이후 회차가 계속 남아있었다.

이 저장소엔 pytest 가 아직 설치/선언돼 있지 않아(requirements.txt 미포함),
test_update_todo_following_scope.py 와 동일하게 직접 실행 가능한 스크립트로 작성한다.

실행:
    python test/test_delete_todo_following_scope.py
"""
import asyncio
import sys
from datetime import datetime, timezone

from app.todo.application.use_cases.delete_todo import DeleteTodoUseCase
from app.todo.domain.models.todo import RecurrenceRule, Todo
from app.todo.domain.models.value_objects import TaskStatus


class FakeTodoRepo:
    """ITodoRepository 를 상속하지 않는 최소 fake — DeleteTodoUseCase 가 실제로 쓰는
    메서드만 구현한다."""

    def __init__(self, seed: list[Todo]) -> None:
        self.by_id: dict[str, Todo] = {t.id: t for t in seed}
        self.deleted_ids: list[str] = []
        self.marked_for_push_ids: list[str] = []

    async def save(self, todo: Todo) -> Todo:
        self.by_id[todo.id] = todo
        return todo

    async def find_by_id(self, id: str, user_id: str) -> Todo | None:
        t = self.by_id.get(id)
        return t if t and t.user_id == user_id else None

    async def find_series_base(self, series_id: str, user_id: str) -> Todo | None:
        t = self.by_id.get(series_id)
        if t and t.user_id == user_id and t.is_series_base:
            return t
        return None

    async def delete(self, todo_id: str, user_id: str) -> None:
        if todo_id in self.by_id:
            del self.by_id[todo_id]
            self.deleted_ids.append(todo_id)

    async def delete_all_exceptions(self, series_id: str, user_id: str) -> None:
        for tid, t in list(self.by_id.items()):
            if t.series_id == series_id and t.user_id == user_id:
                del self.by_id[tid]
                self.deleted_ids.append(tid)

    async def delete_exceptions_from(self, series_id: str, user_id: str, from_date: str) -> None:
        for tid, t in list(self.by_id.items()):
            if (
                t.series_id == series_id
                and t.user_id == user_id
                and (t.original_date_key or t.date_key) >= from_date
            ):
                del self.by_id[tid]
                self.deleted_ids.append(tid)

    async def upsert_exception(self, todo: Todo) -> Todo:  # not exercised here
        self.by_id[todo.id] = todo
        return todo

    async def mark_for_push(self, todo_id: str, user_id: str) -> None:
        self.marked_for_push_ids.append(todo_id)
        t = self.by_id.get(todo_id)
        if t:
            t.calendar_push_status = "pending"
            t.push_intent = "push"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _master(*, linked: bool) -> Todo:
    t = Todo(
        id="todo_master",
        user_id="user_1",
        title="Standup",
        status=TaskStatus.NOT_START,
        date_key="2026-08-01",
        created_at=_now(),
        recurrence_rule=RecurrenceRule(unit="day", interval=1, until=None),
        tags=["work"],
    )
    if linked:
        t.calendar_push_status = "synced"
        t.google_event_id = "gcal_evt_1"
    return t


def _materialized_exception(master: Todo, slot: str) -> Todo:
    return Todo(
        id="todo_exc1",
        user_id=master.user_id,
        title=master.title,
        status=master.status,
        date_key=slot,
        created_at=_now(),
        series_id=master.id,
        original_date_key=slot,
        tags=list(master.tags),
    )


async def test_following_truncates_master_and_repushes_when_calendar_linked():
    master = _master(linked=True)
    repo = FakeTodoRepo([master])
    use_case = DeleteTodoUseCase(repo)

    outcome = await use_case.execute(
        todo_id="todo_master::2026-08-06", user_id="user_1", recurrence_scope="following"
    )

    saved_master = repo.by_id["todo_master"]
    assert saved_master.recurrence_rule is not None
    assert saved_master.recurrence_rule.until == "2026-08-05"

    # 핵심 회귀 검증: 재푸시가 예약되어야 라우터가 push task 를 enqueue 할 수 있다.
    assert "todo_master" in repo.marked_for_push_ids
    assert outcome.push_todo_id == "todo_master"
    assert outcome.delete_google_event_id is None


async def test_following_skips_repush_when_master_not_calendar_linked():
    master = _master(linked=False)
    repo = FakeTodoRepo([master])
    use_case = DeleteTodoUseCase(repo)

    outcome = await use_case.execute(
        todo_id="todo_master::2026-08-06", user_id="user_1", recurrence_scope="following"
    )

    assert repo.marked_for_push_ids == []
    assert outcome.push_todo_id is None


async def test_following_on_materialized_exception_deletes_it_and_truncates_master():
    master = _master(linked=True)
    exc = _materialized_exception(master, "2026-08-06")
    repo = FakeTodoRepo([master, exc])
    use_case = DeleteTodoUseCase(repo)

    outcome = await use_case.execute(todo_id=exc.id, user_id="user_1", recurrence_scope="following")

    assert "todo_exc1" not in repo.by_id
    assert "todo_exc1" in repo.deleted_ids
    assert repo.by_id["todo_master"].recurrence_rule.until == "2026-08-05"
    assert outcome.push_todo_id == "todo_master"


async def test_following_from_first_slot_falls_back_to_full_delete():
    """from_slot 이 base 의 date_key 와 같거나 이전이면 전체 삭제와 동일해야 하며,
    이 경우엔 truncate 가 아니라 delete task 가 enqueue 되어야 한다."""
    master = _master(linked=True)
    repo = FakeTodoRepo([master])
    use_case = DeleteTodoUseCase(repo)

    outcome = await use_case.execute(
        todo_id="todo_master::2026-08-01", user_id="user_1", recurrence_scope="following"
    )

    assert "todo_master" not in repo.by_id
    assert outcome.delete_google_event_id == "gcal_evt_1"
    assert outcome.push_todo_id is None
    assert repo.marked_for_push_ids == []


_TESTS = [
    test_following_truncates_master_and_repushes_when_calendar_linked,
    test_following_skips_repush_when_master_not_calendar_linked,
    test_following_on_materialized_exception_deletes_it_and_truncates_master,
    test_following_from_first_slot_falls_back_to_full_delete,
]


async def _run_all() -> bool:
    ok = True
    for fn in _TESTS:
        try:
            await fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            ok = False
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001 — 스크립트 러너, 실패 원인 그대로 노출
            ok = False
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    return ok


if __name__ == "__main__":
    passed = asyncio.run(_run_all())
    sys.exit(0 if passed else 1)
