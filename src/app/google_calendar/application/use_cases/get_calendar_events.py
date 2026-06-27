from app.google_calendar.application.use_cases.sync_calendar_events import (
    SyncCalendarEventsUseCase,
)
from app.google_calendar.domain.models.calendar_event import CalendarEvent
from app.google_calendar.domain.repositories.repository import ICalendarEventRepository


class GetCalendarEventsUseCase:
    """날짜 범위의 캘린더 이벤트 조회 (온디맨드 sync 포함).

    GET /todos 와 GET /calendar/events 양쪽에서 사용. 미연결 사용자는 빈 리스트.
    sync 가 stale 하면 Google 과 증분 동기화 후 DB 에서 조회. sync 가 실패해도
    저장된(stale) 이벤트를 반환한다.
    """

    def __init__(
        self,
        sync_use_case: SyncCalendarEventsUseCase,
        event_repo: ICalendarEventRepository,
    ) -> None:
        self._sync_use_case = sync_use_case
        self._event_repo = event_repo

    async def execute(
        self, user_id: str, from_date: str, to_date: str
    ) -> list[CalendarEvent]:
        connection = await self._sync_use_case.execute(user_id)
        if connection is None:
            return []
        return await self._event_repo.find_by_date_range(user_id, from_date, to_date)
