from app.todo.application.dtos.commands import UpdateTodoCommand
from app.todo.domain.exceptions.exceptions import TodoNotFoundException
from app.todo.domain.models.todo import Todo
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.domain.repositories.repository import ITodoRepository


class UpdateTodoUseCase:
    def __init__(self, todo_repo: ITodoRepository) -> None:
        self._todo_repo = todo_repo

    async def execute(self, cmd: UpdateTodoCommand) -> Todo:
        todo = await self._todo_repo.find_by_id(cmd.id, cmd.user_id)
        if not todo:
            raise TodoNotFoundException()

        if cmd.title is not None:
            todo.title = cmd.title
        if cmd.description is not None:
            todo.description = cmd.description
        if cmd.date_key is not None:
            todo.move_to(cmd.date_key)
        if cmd.status is not None:
            new_status = TaskStatus(cmd.status)
            if new_status == TaskStatus.DONE:
                todo.complete()
            elif new_status == TaskStatus.IN_PROGRESS:
                todo.start()
            else:
                todo.status = TaskStatus.NOT_START

        return await self._todo_repo.save(todo)
