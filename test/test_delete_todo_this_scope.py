"""
recurrence_scope="this" 삭제 경로 회귀 테스트.

FE 팀 버그 리포트: 가상 인스턴스(합성 id "{base_id}::{slot_date}", DB row 없음)를
scope=this 로 삭제하면 naive PK lookup 이 실패해 404 TODO_NOT_FOUND 가 나고,
낙관적 UI 삭제가 롤백 없이 뒤늦게 되돌아온다는 가설.

검증 결과: DeleteTodoUseCase.execute() 는 is_virtual_id() 로 합성 id 를 먼저 분기해
_delete_virtual() → _cancel_slot() 이 CANCELLED exception row 를 upsert_exception 으로
실체화한다 — naive find_by_id 조회를 거치지 않는다. 즉 소스 코드 상으로는 이미
올바르게 동작한다 (PATCH 의 _materialize_and_update 와 같은 패턴). 이 테스트는 그
동작을 문서화하고 회귀를 방지한다 (a)(b)(c)(d) 커버.

pytest 가 설치돼 있으면 async def test_* 함수들이 그대로 수집된다(asyncio_mode=auto).

실행:
    python test/test_delete_todo_this_scope.py
    pytest test/test_delete_todo_this_scope.py -v
"""
import asyncio
import sys
from datetime import datetime, timezone

from app.todo.application.use_cases.delete_todo import DeleteTodoUseCase
from app.todo.domain.models.todo import RecurrenceRule, Todo
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.domain.exceptions.exceptions import TodoNotFoundException


class FakeTodoRepo:
    """ITodoRepository 를 상속하지 않는 최소 fake — DeleteTodoUseCase 가 실제로 쓰는
    메서드만 구현한다 (test_delete_todo_following_scope.py 와 동일 패턴)."""

    def __init__(self, seed: list[Todo]) -> None:
        self.by_id: dict[str, Todo] = {t.id: t for t in seed}
        self.deleted_ids: list[str] = []
        self.marked_for_push_ids: list[str] = []
        self.upserted_exceptions: list[Todo] = []

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

    async def upsert_exception(self, todo: Todo) -> Todo:
        # 실제 repo 는 (series_id, original_date_key) 로 ON CONFLICT upsert 하지만,
        # 이 fake 는 이미 같은 슬롯에 실체화된 row 가 있으면 그 row 를 갱신(대체)한다 —
        # DeleteTodoUseCase 가 항상 새 id 로 생성해 넘기므로, 실제 DB 의 유니크 제약과
        # 동일하게 "슬롯당 하나"를 보장하려면 여기서 series_id+original_date_key 로
        # 기존 row 를 찾아 대체해야 한다.
        for tid, existing in list(self.by_id.items()):
            if (
                existing.series_id == todo.series_id
                and existing.original_date_key == todo.original_date_key
                and tid != todo.id
            ):
                del self.by_id[tid]
        self.by_id[todo.id] = todo
        self.upserted_exceptions.append(todo)
        return todo

    async def mark_for_push(self, todo_id: str, user_id: str) -> None:
        self.marked_for_push_ids.append(todo_id)
        t = self.by_id.get(todo_id)
        if t:
            t.calendar_push_status = "pending"
            t.push_intent = "push"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _master(*, linked: bool = False) -> Todo:
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


def _materialized_exception(master: Todo, slot: str, *, status: TaskStatus = TaskStatus.NOT_START) -> Todo:
    return Todo(
        id="todo_exc1",
        user_id=master.user_id,
        title=master.title,
        status=status,
        date_key=slot,
        created_at=_now(),
        series_id=master.id,
        original_date_key=slot,
        tags=list(master.tags),
    )


# (a) 가상/미실체화 회차 — scope=this 는 404 가 아니라 CANCELLED exception row 를
#     생성해야 한다 (naive PK lookup 가설 반증).
async def test_this_scope_on_virtual_instance_materializes_cancelled_exception():
    master = _master(linked=False)
    repo = FakeTodoRepo([master])
    use_case = DeleteTodoUseCase(repo)

    outcome = await use_case.execute(
        todo_id="todo_master::2026-08-06", user_id="user_1", recurrence_scope="this"
    )

    # 404 가 아니라 정상 완료돼야 한다.
    assert len(repo.upserted_exceptions) == 1
    exc = repo.upserted_exceptions[0]
    assert exc.status == TaskStatus.CANCELLED
    assert exc.series_id == "todo_master"
    assert exc.original_date_key == "2026-08-06"
    assert exc.date_key == "2026-08-06"
    # master 자신은 그대로 남아있다 (this == 슬롯 하나만 취소).
    assert "todo_master" in repo.by_id
    assert outcome.delete_google_event_id is None  # 캘린더 미연동


async def test_this_scope_on_virtual_instance_of_calendar_linked_series_returns_gcal_instance_id():
    master = _master(linked=True)
    repo = FakeTodoRepo([master])
    use_case = DeleteTodoUseCase(repo)

    outcome = await use_case.execute(
        todo_id="todo_master::2026-08-06", user_id="user_1", recurrence_scope="this"
    )

    assert len(repo.upserted_exceptions) == 1
    assert outcome.delete_google_event_id is not None
    assert outcome.delete_google_event_id.startswith("gcal_evt_1_")


# (b) 이미 실체화된 exception row — scope=this 는 그 row 자체를 삭제해야 한다
#     (새로 upsert 하지 않는다).
async def test_this_scope_on_materialized_exception_deletes_that_row_only():
    master = _master(linked=False)
    exc = _materialized_exception(master, "2026-08-06")
    repo = FakeTodoRepo([master, exc])
    use_case = DeleteTodoUseCase(repo)

    outcome = await use_case.execute(todo_id=exc.id, user_id="user_1", recurrence_scope="this")

    assert "todo_exc1" not in repo.by_id
    assert "todo_exc1" in repo.deleted_ids
    assert repo.upserted_exceptions == []  # 새 CANCELLED row 를 만들지 않는다
    assert "todo_master" in repo.by_id  # master 는 영향 없음
    assert outcome.delete_google_event_id is None


# (c) 비반복(일반) todo — scope=this(default) 는 기존과 동일하게 그냥 삭제돼야 한다.
async def test_this_scope_on_non_recurring_todo_deletes_normally():
    todo = Todo(
        id="todo_plain1",
        user_id="user_1",
        title="장보기",
        status=TaskStatus.NOT_START,
        date_key="2026-08-06",
        created_at=_now(),
    )
    repo = FakeTodoRepo([todo])
    use_case = DeleteTodoUseCase(repo)

    outcome = await use_case.execute(todo_id="todo_plain1", user_id="user_1")  # scope 기본값 "this"

    assert "todo_plain1" not in repo.by_id
    assert "todo_plain1" in repo.deleted_ids
    assert outcome.delete_google_event_id is None


# (d) following/all 스코프는 여전히 동작해야 한다 (virtual id 기준).
async def test_all_scope_on_virtual_instance_deletes_entire_series():
    master = _master(linked=True)
    exc = _materialized_exception(master, "2026-08-06")
    repo = FakeTodoRepo([master, exc])
    use_case = DeleteTodoUseCase(repo)

    outcome = await use_case.execute(
        todo_id="todo_master::2026-08-13", user_id="user_1", recurrence_scope="all"
    )

    assert "todo_master" not in repo.by_id
    assert "todo_exc1" not in repo.by_id
    assert outcome.delete_google_event_id == "gcal_evt_1"


async def test_following_scope_on_virtual_instance_truncates_series():
    master = _master(linked=False)
    repo = FakeTodoRepo([master])
    use_case = DeleteTodoUseCase(repo)

    outcome = await use_case.execute(
        todo_id="todo_master::2026-08-06", user_id="user_1", recurrence_scope="following"
    )

    assert repo.by_id["todo_master"].recurrence_rule.until == "2026-08-05"
    assert outcome.delete_google_event_id is None


# 존재하지 않는 시리즈의 가상 id → 여전히 TODO_NOT_FOUND 여야 한다 (실제 404 케이스).
async def test_this_scope_on_virtual_instance_of_unknown_series_raises_not_found():
    repo = FakeTodoRepo([])
    use_case = DeleteTodoUseCase(repo)

    try:
        await use_case.execute(
            todo_id="todo_ghost::2026-08-06", user_id="user_1", recurrence_scope="this"
        )
        raise AssertionError("TodoNotFoundException 이 발생해야 한다")
    except TodoNotFoundException:
        pass


# base row 를 직접 this 로 삭제 → base 는 남고 첫 슬롯만 취소돼야 한다.
async def test_this_scope_on_series_base_row_directly_cancels_first_slot():
    master = _master(linked=False)
    repo = FakeTodoRepo([master])
    use_case = DeleteTodoUseCase(repo)

    outcome = await use_case.execute(todo_id="todo_master", user_id="user_1", recurrence_scope="this")

    assert "todo_master" in repo.by_id  # base 자체는 유지
    assert len(repo.upserted_exceptions) == 1
    assert repo.upserted_exceptions[0].original_date_key == "2026-08-01"
    assert repo.upserted_exceptions[0].status == TaskStatus.CANCELLED


_TESTS = [
    test_this_scope_on_virtual_instance_materializes_cancelled_exception,
    test_this_scope_on_virtual_instance_of_calendar_linked_series_returns_gcal_instance_id,
    test_this_scope_on_materialized_exception_deletes_that_row_only,
    test_this_scope_on_non_recurring_todo_deletes_normally,
    test_all_scope_on_virtual_instance_deletes_entire_series,
    test_following_scope_on_virtual_instance_truncates_series,
    test_this_scope_on_virtual_instance_of_unknown_series_raises_not_found,
    test_this_scope_on_series_base_row_directly_cancels_first_slot,
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
