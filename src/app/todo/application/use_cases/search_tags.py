from app.todo.application.dtos.queries import SearchTagsQuery
from app.todo.domain.repositories.repository import ITodoRepository


class SearchTagsUseCase:
    def __init__(self, todo_repo: ITodoRepository) -> None:
        self._todo_repo = todo_repo

    async def execute(self, query: SearchTagsQuery) -> list[str]:
        return await self._todo_repo.search_tags(
            user_id=query.user_id, query=query.query, limit=query.limit
        )
