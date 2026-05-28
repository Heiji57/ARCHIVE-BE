from app.todo.application.dtos.queries import GetTodosByRangeQuery
from app.todo.domain.models.todo import Todo
from app.todo.domain.repositories.repository import ITodoRepository


class GetTodosByRangeUseCase:
    def __init__(self, todo_repo: ITodoRepository) -> None:
        self._todo_repo = todo_repo

    async def execute(self, query: GetTodosByRangeQuery) -> list[Todo]:
        return await self._todo_repo.find_by_date_range(
            query.user_id, query.from_date, query.to_date
        )
