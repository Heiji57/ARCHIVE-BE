from app.google_calendar.domain.repositories.repository import (
    ICalendarEventRepository,
    IGoogleCalendarConnectionRepository,
)
from app.todo.domain.repositories.repository import ITodoRepository


class DisconnectCalendarUseCase:
    """Google Calendar 연결 해제 — connection + 저장된 이벤트 전체 삭제.

    연동돼 있던 todo 들의 push 상태도 초기화한다 — 연결이 사라졌는데 todo 가
    synced/pending 등으로 남아 존재하지 않는 연결을 가리키지 않도록.
    """

    def __init__(
        self,
        connection_repo: IGoogleCalendarConnectionRepository,
        event_repo: ICalendarEventRepository,
        todo_repo: ITodoRepository,
    ) -> None:
        self._connection_repo = connection_repo
        self._event_repo = event_repo
        self._todo_repo = todo_repo

    async def execute(self, user_id: str) -> None:
        await self._todo_repo.bulk_clear_calendar_push(user_id)
        await self._event_repo.delete_all_by_user(user_id)
        await self._connection_repo.delete_by_user_id(user_id)
