from datetime import datetime, timezone

from app.shared.domain.utils.id import generate_id
from app.todo.application.dtos.commands import CreateTodoCommand
from app.todo.domain.models.todo import Todo
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.domain.repositories.repository import ITodoRepository


class CreateTodoUseCase:
    def __init__(self, todo_repo: ITodoRepository) -> None:
        self._todo_repo = todo_repo

    async def execute(self, cmd: CreateTodoCommand) -> Todo:
        now = datetime.now(timezone.utc)
        todo = Todo(
            id=generate_id("todo"),
            user_id=cmd.user_id,
            title=cmd.title,
            status=TaskStatus(cmd.status),
            date_key=cmd.date_key,
            description=cmd.description,
            start_time=cmd.start_time,
            end_time=cmd.end_time,
            created_at=now,
        )
        return await self._todo_repo.save(todo)
