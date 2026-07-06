from app.todo.domain.exceptions.exceptions import TodoNotFoundException
from app.todo.domain.repositories.repository import ITodoRepository


class DeleteTodoUseCase:
    def __init__(self, todo_repo: ITodoRepository) -> None:
        self._todo_repo = todo_repo

    async def execute(self, todo_id: str, user_id: str) -> str | None:
        """todo 삭제 후, 연동돼 있던 Google event id 를 반환한다.

        반환값이 non-null 이면 라우터가 best-effort 삭제 task 를 enqueue 한다.
        todo 행은 즉시 삭제하므로 push 상태 추적은 불필요(잔여 orphan 은 삭제 task 재시도).
        """
        todo = await self._todo_repo.find_by_id(todo_id, user_id)
        if not todo:
            raise TodoNotFoundException()
        google_event_id = todo.google_event_id
        await self._todo_repo.delete(todo_id, user_id)
        return google_event_id
