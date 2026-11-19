"""AI 포트 → 할 일 모듈. 쓰기는 할 일 묶음 수정 유스케이스와 같은 후속 작업을 그대로 탄다."""

from dataclasses import replace
from datetime import datetime
from typing import Any

from app.ai.domain.models.snapshots import TodoSnapshot
from app.shared.domain.utils.unset import UNSET
from app.todo.application.dtos.commands import CreateTodoCommand, UpdateTodoCommand
from app.todo.application.dtos.queries import (
    GetTodosByDateQuery,
    GetTodosByRangeQuery,
    GetTodosFilteredQuery,
)
from app.todo.application.ports import TodoChangeObserver
from app.todo.application.use_cases.batch_update_todos import BatchUpdateTodosUseCase
from app.todo.application.use_cases.create_todo import CreateTodoUseCase
from app.todo.application.use_cases.delete_todo import DeleteTodoUseCase
from app.todo.application.use_cases.get_todos_by_date import GetTodosByDateUseCase
from app.todo.application.use_cases.get_todos_by_range import GetTodosByRangeUseCase
from app.todo.application.use_cases.get_todos_filtered import GetTodosFilteredUseCase
from app.todo.application.use_cases.trash import TodoTrashUseCase
from app.todo.domain.models.todo import Todo
from app.todo.domain.repositories.repository import ITodoRepository
from app.todo.domain.utils.recurrence import is_virtual_id, make_virtual, parse_virtual_id
from app.todo.infrastructure.side_effects import after_update, enqueue_delete, enqueue_push
from app.topic.domain.repositories.repository import (
    IEmbeddingQueueRepository,
    ITodoEmbeddingRepository,
)

_PATCHABLE = ("date_key", "due_date_key", "status", "start_time", "end_time", "timezone")


def to_snapshot(t: Todo) -> TodoSnapshot:
    return TodoSnapshot(
        id=t.id,
        title=t.title,
        date_key=t.date_key,
        status=t.status.value,
        start_time=t.start_time,
        end_time=t.end_time,
        timezone=t.timezone,
        due_date_key=t.due_date_key,
        tags=tuple(t.tags),
        recurring=t.series_id is not None or is_virtual_id(t.id) or t.is_series_base,
    )


def to_update_command(user_id: str, todo_id: str, patch: dict[str, Any]) -> UpdateTodoCommand:
    """AI 가 만든 patch(dict) → 할 일 수정 명령. 보내지 않은 필드는 UNSET(그대로)."""
    unknown = set(patch) - set(_PATCHABLE)
    if unknown:
        raise ValueError(f"unsupported patch fields: {sorted(unknown)}")

    def dt(value: Any) -> datetime | None:
        return datetime.fromisoformat(value) if isinstance(value, str) else value

    return UpdateTodoCommand(
        id=todo_id,
        user_id=user_id,
        date_key=patch.get("date_key"),
        status=patch.get("status"),
        due_date_key=patch["due_date_key"] if "due_date_key" in patch else UNSET,
        start_time=dt(patch["start_time"]) if "start_time" in patch else UNSET,
        end_time=dt(patch["end_time"]) if "end_time" in patch else UNSET,
        timezone=patch["timezone"] if "timezone" in patch else UNSET,
    )


class TodoAdapter:
    def __init__(
        self,
        todo_repo: ITodoRepository,
        batch_uc: BatchUpdateTodosUseCase,
        queue_repo: IEmbeddingQueueRepository,
        create_uc: CreateTodoUseCase,
        delete_uc: DeleteTodoUseCase,
        todo_emb_repo: ITodoEmbeddingRepository,
        trash_uc: TodoTrashUseCase,
        observer: TodoChangeObserver,
    ) -> None:
        self._repo = todo_repo
        self._batch = batch_uc
        self._queue = queue_repo
        self._create = create_uc
        self._delete = delete_uc
        self._emb = todo_emb_repo
        self._trash = trash_uc
        self._observer = observer

    async def list_on(self, user_id: str, date_key: str) -> list[TodoSnapshot]:
        todos = await GetTodosByDateUseCase(self._repo).execute(
            GetTodosByDateQuery(user_id=user_id, date_key=date_key)
        )
        return [to_snapshot(t) for t in todos]

    async def list_overdue(
        self, user_id: str, tz: str, limit: int, today: str | None = None
    ) -> list[TodoSnapshot]:
        todos = await GetTodosFilteredUseCase(self._repo).execute(
            GetTodosFilteredQuery(user_id=user_id, tz=tz, overdue=True, size=limit, today=today)
        )
        return [to_snapshot(t) for t in todos]

    async def get(self, user_id: str, todo_id: str) -> TodoSnapshot | None:
        if is_virtual_id(todo_id):
            base_id, slot = parse_virtual_id(todo_id)
            base = await self._repo.find_series_base(base_id, user_id)
            if base is None:
                return None
            # 그 회차를 사용자가 이미 고쳐 둔 예외 row 가 있으면 그 값이 "지금 값"이다.
            exceptions = await self._repo.find_exceptions_batch(user_id, [base.id], slot, slot)
            exc = next((e for e in exceptions if e.original_date_key == slot), None)
            if exc is not None:
                return replace(to_snapshot(exc), id=todo_id)
            return to_snapshot(make_virtual(base, slot))
        todo = await self._repo.find_by_id(todo_id, user_id)
        return to_snapshot(todo) if todo else None

    async def apply_patch(
        self, user_id: str, todo_id: str, patch: dict[str, Any], observe: bool = True
    ) -> str:
        result = await self._batch.execute(user_id, [to_update_command(user_id, todo_id, patch)])
        outcome = result.outcomes[0]
        await after_update(
            self._queue,
            user_id,
            outcome.todo,
            outcome.extra_push_todo_id,
            before=outcome.before,
            observer=self._observer if observe else None,
        )
        return outcome.todo.id

    async def list_range(self, user_id: str, from_key: str, to_key: str) -> list[TodoSnapshot]:
        todos = await GetTodosByRangeUseCase(self._repo).execute(
            GetTodosByRangeQuery(user_id=user_id, from_date=from_key, to_date=to_key)
        )
        return [to_snapshot(t) for t in todos]

    async def create(
        self,
        user_id: str,
        title: str,
        date_key: str,
        start_time: datetime | None,
        end_time: datetime | None,
        timezone: str | None,
    ) -> str:
        """POST /todos 와 같은 후속 작업(Google push 예약, 임베딩)까지."""
        todo = await self._create.execute(
            CreateTodoCommand(
                user_id=user_id,
                title=title,
                date_key=date_key,
                start_time=start_time,
                end_time=end_time,
                timezone=timezone if start_time or end_time else None,
            )
        )
        if todo.calendar_push_status in ("pending", "pending_delete"):
            enqueue_push(user_id, todo.id)
        if not todo.is_series_base:
            await self._queue.enqueue("todo", todo.id, user_id)
        return todo.id

    async def delete(self, user_id: str, todo_id: str) -> None:
        """DELETE /todos/{id}(이번 회차)와 같은 후속 작업(Google 일정 정리, 임베딩 삭제)까지."""
        outcome = await self._delete.execute(todo_id=todo_id, user_id=user_id)
        if outcome.delete_google_event_id:
            enqueue_delete(user_id, outcome.delete_google_event_id)
        if outcome.push_todo_id:
            enqueue_push(user_id, outcome.push_todo_id)
        await self._emb.delete_by_todo(todo_id)

    async def restore(self, user_id: str, todo_id: str) -> bool:
        """휴지통 되살리기(`POST /trash/todo/{id}/restore`)와 같은 후속 작업 — push·임베딩."""
        restored = await self._trash.restore(user_id, todo_id)
        if restored is None:
            return False
        if restored.push:
            enqueue_push(user_id, todo_id)
        if not restored.todo.is_series_base:
            await self._queue.enqueue("todo", todo_id, user_id)
        return True
