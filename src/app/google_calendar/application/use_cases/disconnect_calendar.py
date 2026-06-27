from app.google_calendar.domain.repositories.repository import (
    ICalendarEventRepository,
    IGoogleCalendarConnectionRepository,
)


class DisconnectCalendarUseCase:
    """Google Calendar 연결 해제 — connection + 저장된 이벤트 전체 삭제."""

    def __init__(
        self,
        connection_repo: IGoogleCalendarConnectionRepository,
        event_repo: ICalendarEventRepository,
    ) -> None:
        self._connection_repo = connection_repo
        self._event_repo = event_repo

    async def execute(self, user_id: str) -> None:
        await self._event_repo.delete_all_by_user(user_id)
        await self._connection_repo.delete_by_user_id(user_id)
