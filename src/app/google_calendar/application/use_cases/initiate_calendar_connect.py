from app.google_calendar.infrastructure.api.google_calendar_client import (
    GoogleCalendarApiClient,
)
from app.google_calendar.infrastructure.cache.calendar_state import (
    CalendarOAuthStateCache,
)


class InitiateCalendarConnectUseCase:
    """Google Calendar 연결 authorize URL 생성.

    인증된 사용자가 호출 → state 에 user_id 저장 → FE 가 응답 URL 을 popup 으로 연다.
    """

    def __init__(
        self,
        api_client: GoogleCalendarApiClient,
        state_cache: CalendarOAuthStateCache,
    ) -> None:
        self._api_client = api_client
        self._state_cache = state_cache

    async def execute(self, user_id: str) -> str:
        state = await self._state_cache.create_state(user_id)
        return self._api_client.build_authorize_url(state)
