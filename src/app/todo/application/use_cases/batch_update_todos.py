import copy
from dataclasses import dataclass

from fastapi.exceptions import RequestValidationError

from app.shared.domain.exceptions.base import BaseAppException
from app.todo.application.dtos.commands import UpdateTodoCommand
from app.todo.application.use_cases.update_todo import UpdateTodoOutcome, UpdateTodoUseCase
from app.todo.domain.exceptions.exceptions import (
    TodoBatchFailedException,
    TodoNotFoundException,
)
from app.todo.domain.models.todo import Todo
from app.todo.domain.repositories.repository import ITodoRepository
from app.todo.domain.utils.recurrence import is_virtual_id, make_virtual, parse_virtual_id


@dataclass(frozen=True)
class BatchUpdateResult:
    outcomes: list[UpdateTodoOutcome]
    # 변경 전 스냅샷 — FE "되돌리기"가 그대로 다시 묶음 수정에 넣는다. 순서는 operations 와 같다.
    previous: list[Todo]


class BatchUpdateTodosUseCase:
    """여러 todo 를 한 트랜잭션에서 수정한다 (전부 아니면 전무).

    건별 규칙은 단건 수정(`UpdateTodoUseCase`)을 그대로 쓴다. 요청 스코프 세션이
    `factory.begin()` 트랜잭션이라, 예외를 던지면 앞선 변경까지 함께 롤백된다.
    하나라도 실패하면 나머지도 끝까지 검사해 건별 실패 이유를 모아 던진다.

    `previous` 는 **묶음 전** 상태다 — 모든 대상을 먼저 읽어 둔 뒤 적용한다. 건마다
    직전에 읽으면 앞 건(예: 시리즈 전체 수정)이 바꾼 값이 뒤 건의 "변경 전"으로 잡힌다.
    같은 시리즈를 여러 건이 건드리면 순서대로 적용된다(앞 건이 지운 예외 row 를 뒤 건이
    가리키면 그 건은 TODO_NOT_FOUND).
    """

    def __init__(self, todo_repo: ITodoRepository, update_uc: UpdateTodoUseCase) -> None:
        self._todo_repo = todo_repo
        self._update_uc = update_uc

    async def execute(self, user_id: str, commands: list[UpdateTodoCommand]) -> BatchUpdateResult:
        outcomes: list[UpdateTodoOutcome] = []
        previous: list[Todo] = []
        failures: list[dict[str, str]] = []
        missing: set[str] = set()
        for cmd in commands:
            try:
                previous.append(await self._snapshot(cmd.id, user_id))
            except BaseAppException as e:
                failures.append({"id": cmd.id, "code": e.code})
                missing.add(cmd.id)
        for cmd in commands:
            if cmd.id in missing:
                continue
            try:
                outcomes.append(await self._update_uc.execute(cmd))
            except BaseAppException as e:
                failures.append({"id": cmd.id, "code": e.code})
            except RequestValidationError:
                failures.append({"id": cmd.id, "code": "VALIDATION_ERROR"})
        if failures:
            raise TodoBatchFailedException("Batch update failed.", details=failures)
        return BatchUpdateResult(outcomes=outcomes, previous=previous)

    async def _snapshot(self, todo_id: str, user_id: str) -> Todo:
        if is_virtual_id(todo_id):
            base_id, slot = parse_virtual_id(todo_id)
            master = await self._todo_repo.find_series_base(base_id, user_id)
            if master is None:
                raise TodoNotFoundException()
            return make_virtual(master, slot)
        todo = await self._todo_repo.find_by_id(todo_id, user_id)
        if todo is None:
            raise TodoNotFoundException()
        # 수정이 같은 엔티티를 제자리에서 바꾸므로 복사해 둔다.
        return copy.deepcopy(todo)
