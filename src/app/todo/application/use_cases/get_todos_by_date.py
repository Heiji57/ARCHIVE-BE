from app.todo.application.dtos.queries import GetTodosByDateQuery
from app.todo.domain.models.todo import Todo
from app.todo.domain.repositories.repository import ITodoRepository


class GetTodosByDateUseCase:
    def __init__(self, todo_repo: ITodoRepository) -> None:
        self._todo_repo = todo_repo

    async def execute(self, query: GetTodosByDateQuery) -> list[Todo]:
        return await self._todo_repo.find_by_date_key(query.user_id, query.date_key)
