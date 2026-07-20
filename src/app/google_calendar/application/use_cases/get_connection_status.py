from dataclasses import dataclass
from datetime import datetime

from app.google_calendar.domain.repositories.repository import (
    IGoogleCalendarConnectionRepository,
)


@dataclass(frozen=True)
class CalendarConnectionStatus:
    connected: bool
    needs_reauth: bool
    google_user_id: str | None
    last_synced_at: datetime | None


class GetCalendarConnectionStatusUseCase:
    """Google Calendar 연결 상태 조회.

    connected=True 이고 needs_reauth=True 면 토큰이 무효해진 상태 → FE 재연결 유도.
    """

    def __init__(self, connection_repo: IGoogleCalendarConnectionRepository) -> None:
        self._connection_repo = connection_repo

    async def execute(self, user_id: str) -> CalendarConnectionStatus:
        conn = await self._connection_repo.find_by_user_id(user_id)
        if conn is None:
            return CalendarConnectionStatus(
                connected=False,
                needs_reauth=False,
                google_user_id=None,
                last_synced_at=None,
            )
        return CalendarConnectionStatus(
            connected=True,
            needs_reauth=conn.needs_reauth,
            google_user_id=conn.google_user_id,
            last_synced_at=conn.last_synced_at,
        )
