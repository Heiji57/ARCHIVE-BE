from app.todo.domain.exceptions.exceptions import TodoNotFoundException
from app.todo.domain.repositories.repository import ITodoRepository


class AddCalendarLinkUseCase:
    """기존 todo 를 Google Calendar 에 연동(사이드바 '캘린더에 추가').

    mark_for_push 로 pending 예약 → push 루틴이 이벤트 생성. 이미 연동/synced 여도
    재-push(update)로 멱등 처리. sync_attempt_id 무효화로 진행 중 push 와 안전.
    """

    def __init__(self, todo_repo: ITodoRepository) -> None:
        self._todo_repo = todo_repo

    async def execute(self, todo_id: str, user_id: str) -> None:
        todo = await self._todo_repo.find_by_id(todo_id, user_id)
        if not todo:
            raise TodoNotFoundException()
        await self._todo_repo.mark_for_push(todo_id, user_id)
