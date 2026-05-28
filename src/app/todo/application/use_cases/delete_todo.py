from app.todo.domain.exceptions.exceptions import TodoNotFoundException
from app.todo.domain.repositories.repository import ITodoRepository


class DeleteTodoUseCase:
    def __init__(self, todo_repo: ITodoRepository) -> None:
        self._todo_repo = todo_repo

    async def execute(self, todo_id: str, user_id: str) -> None:
        todo = await self._todo_repo.find_by_id(todo_id, user_id)
        if not todo:
            raise TodoNotFoundException()
        await self._todo_repo.delete(todo_id, user_id)
