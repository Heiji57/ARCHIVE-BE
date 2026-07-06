from app.todo.domain.exceptions.exceptions import TodoNotFoundException
from app.todo.domain.repositories.repository import ITodoRepository


class RemoveCalendarLinkUseCase:
    """todo 는 유지한 채 Google Calendar 연동만 해제(사이드바 '캘린더에서 빼기').

    pending_delete 로 마킹 → push 루틴이 Google 이벤트를 삭제하고 완전 unlink.
    mark_for_delete 가 sync_attempt_id 를 NULL 로 무효화하므로 진행 중이던 push
    finalize 는 no-op 되고, 다음 사이클이 삭제를 수행한다.
    """

    def __init__(self, todo_repo: ITodoRepository) -> None:
        self._todo_repo = todo_repo

    async def execute(self, todo_id: str, user_id: str) -> bool:
        """연동 해제를 예약했으면 True(라우터가 즉시 push task enqueue), 미연동이면 False."""
        todo = await self._todo_repo.find_by_id(todo_id, user_id)
        if not todo:
            raise TodoNotFoundException()
        if todo.calendar_push_status is None:
            return False  # 애초에 미연동 — no-op
        await self._todo_repo.mark_for_delete(todo_id, user_id)
        return True
