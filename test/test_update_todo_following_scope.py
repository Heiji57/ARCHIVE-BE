"""
반복 시리즈의 이미 실체화된 예외 row 를 recurrence_scope="following" 으로 수정할 때
새 시리즈로 올바르게 분리되는지 검증한다 (버그: 기존엔 _update_real 로 빠져
scope 가 무시되고 "this" 처럼 그 row 하나만 패치됐음).

이 저장소엔 pytest 가 아직 설치/선언돼 있지 않아(requirements.txt 미포함),
test_md_output.py 와 동일하게 직접 실행 가능한 스크립트로 작성한다.
pytest 가 나중에 추가되면 async def test_* 함수들이 그대로 수집된다.

실행:
    python test/test_update_todo_following_scope.py
"""
import asyncio
import sys
from datetime import datetime, timezone

from app.todo.application.dtos.commands import UpdateTodoCommand
from app.todo.application.use_cases.update_todo import UpdateTodoUseCase
from app.todo.domain.models.todo import RecurrenceRule, Todo
from app.todo.domain.models.value_objects import TaskStatus


class FakeTodoRepo:
    """ITodoRepository 를 상속하지 않는 최소 fake — UpdateTodoUseCase 가 실제로 쓰는
    메서드(save/find_by_id/find_series_base/delete_exceptions_from)만 구현한다."""

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


def _master() -> Todo:
    return Todo(
        id="todo_master",
        user_id="user_1",
        title="Standup",
        status=TaskStatus.NOT_START,
        date_key="2026-08-01",
        created_at=_now(),
        recurrence_rule=RecurrenceRule(unit="day", interval=1, until=None),
        tags=["work"],
    )


def _materialized_exception(master: Todo, slot: str) -> Todo:
    """이미 한 번 "this" 스코프로 실체화된 예외 row — 버그 리포트의 실제 응답과
    동일한 모양(series_id 있음, recurrence_rule None, is_virtual 아님)."""
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


async def test_following_on_materialized_exception_splits_new_series():
    master = _master()
    exc = _materialized_exception(master, "2026-08-06")
    repo = FakeTodoRepo([master, exc])
    use_case = UpdateTodoUseCase(repo)

    cmd = UpdateTodoCommand(
        id=exc.id,
        user_id="user_1",
        recurrence_scope="following",
        tags=["work", "urgent"],
    )
    result = (await use_case.execute(cmd)).todo

    # 버그였던 부분: recurrence_rule 이 채워져 있고(제대로 된 새 base), series_id 는 None.
    assert result.recurrence_rule is not None, "새 base 여야 하는데 recurrence_rule 이 없음"
    assert result.series_id is None, "새 base 여야 하는데 여전히 예외 row 로 남음"
    assert result.id not in ("todo_master", "todo_exc1"), "새로 생성된 id 여야 함"
    assert result.date_key == "2026-08-06"
    assert result.tags == ["work", "urgent"], "patch 가 적용돼야 함"
    assert result.title == "Standup", "예외 row 의 기존 내용을 baseline 으로 이어받아야 함"

    # 기존 exception row 는 분리 과정에서 정리되어야 함.
    assert "todo_exc1" not in repo.by_id
    assert "todo_exc1" in repo.deleted_ids

    # 원래 master 의 until 은 분리 지점 전날로 truncate 되어야 함.
    saved_master = repo.by_id["todo_master"]
    assert saved_master.recurrence_rule is not None
    assert saved_master.recurrence_rule.until == "2026-08-05"


async def test_following_preserves_exception_own_time_not_master_pattern():
    """예외 row 가 이미 개별적으로 시간을 바꿔둔 상태였다면(this 스코프), following 분리 시
    master 의 시간 패턴으로 되돌아가지 않고 그 예외 row 자신의 시간을 이어받아야 한다."""
    master = _master()
    exc = _materialized_exception(master, "2026-08-06")
    exc.start_time = datetime(2026, 8, 6, 15, 0, tzinfo=timezone.utc)
    exc.end_time = datetime(2026, 8, 6, 16, 0, tzinfo=timezone.utc)
    repo = FakeTodoRepo([master, exc])
    use_case = UpdateTodoUseCase(repo)

    cmd = UpdateTodoCommand(
        id=exc.id, user_id="user_1", recurrence_scope="following", title="Standup v2"
    )
    result = (await use_case.execute(cmd)).todo

    assert result.start_time == exc.start_time
    assert result.end_time == exc.end_time
    assert result.title == "Standup v2"


async def test_virtual_instance_following_unchanged_regression():
    """기존에 이미 동작하던 가상 인스턴스 경로(virtual id)는 그대로 동작해야 한다 —
    새 base 의 baseline 이 master 에서 오는지 확인 (source=None 경로 회귀 방지)."""
    master = _master()
    repo = FakeTodoRepo([master])
    use_case = UpdateTodoUseCase(repo)

    cmd = UpdateTodoCommand(
        id="todo_master::2026-08-13",
        user_id="user_1",
        recurrence_scope="following",
        tags=["work", "later"],
    )
    result = (await use_case.execute(cmd)).todo

    assert result.recurrence_rule is not None
    assert result.series_id is None
    assert result.date_key == "2026-08-13"
    assert result.title == master.title  # baseline 은 master 에서
    assert result.tags == ["work", "later"]  # patch 는 적용됨

    saved_master = repo.by_id["todo_master"]
    assert saved_master.recurrence_rule.until == "2026-08-12"


async def test_following_repushes_truncated_master_when_calendar_linked():
    """버그: GCal 에 연동된 시리즈를 "following" 으로 분리하면 옛 master 의 until 이
    truncate 되어 저장은 되지만, 그 사실이 Google 에 재푸시되지 않아 캘린더에 남은
    회차가 그대로 남아있었다. mark_for_push 가 호출되어야 한다."""
    master = _master()
    master.calendar_push_status = "synced"
    master.google_event_id = "gcal_evt_1"
    exc = _materialized_exception(master, "2026-08-06")
    repo = FakeTodoRepo([master, exc])
    use_case = UpdateTodoUseCase(repo)

    cmd = UpdateTodoCommand(
        id=exc.id, user_id="user_1", recurrence_scope="following", tags=["work", "urgent"]
    )
    outcome = await use_case.execute(cmd)

    assert "todo_master" in repo.marked_for_push_ids
    saved_master = repo.by_id["todo_master"]
    assert saved_master.calendar_push_status == "pending"

    # 라우터가 즉시 push_calendar_event_task 를 enqueue 할 수 있도록, 응답 엔티티
    # (새로 분리된 base)와 별개로 옛 master 의 id 가 신호되어야 한다.
    assert outcome.extra_push_todo_id == "todo_master"
    assert outcome.todo.id not in ("todo_master", "todo_exc1")


async def test_following_skips_repush_when_master_not_calendar_linked():
    """회귀 방지: GCal 미연동 시리즈는 mark_for_push 를 호출하지 않아야 한다."""
    master = _master()
    exc = _materialized_exception(master, "2026-08-06")
    repo = FakeTodoRepo([master, exc])
    use_case = UpdateTodoUseCase(repo)

    cmd = UpdateTodoCommand(
        id=exc.id, user_id="user_1", recurrence_scope="following", tags=["work", "urgent"]
    )
    outcome = await use_case.execute(cmd)

    assert repo.marked_for_push_ids == []
    assert outcome.extra_push_todo_id is None


async def test_this_scope_on_materialized_exception_still_patches_single_row():
    """회귀 방지: "this" 스코프는 여전히 그 예외 row 하나만 패치해야 한다(분리 X)."""
    master = _master()
    exc = _materialized_exception(master, "2026-08-06")
    repo = FakeTodoRepo([master, exc])
    use_case = UpdateTodoUseCase(repo)

    cmd = UpdateTodoCommand(
        id=exc.id, user_id="user_1", recurrence_scope="this", tags=["work", "just-this"]
    )
    result = (await use_case.execute(cmd)).todo

    assert result.id == "todo_exc1"
    assert result.series_id == "todo_master"
    assert result.recurrence_rule is None
    assert result.tags == ["work", "just-this"]
    # master 는 건드리지 않아야 함
    assert repo.by_id["todo_master"].recurrence_rule.until is None


_TESTS = [
    test_following_on_materialized_exception_splits_new_series,
    test_following_preserves_exception_own_time_not_master_pattern,
    test_virtual_instance_following_unchanged_regression,
    test_following_repushes_truncated_master_when_calendar_linked,
    test_following_skips_repush_when_master_not_calendar_linked,
    test_this_scope_on_materialized_exception_still_patches_single_row,
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
