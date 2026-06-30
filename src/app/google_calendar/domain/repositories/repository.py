from abc import ABC, abstractmethod
from datetime import datetime

from app.google_calendar.domain.models.calendar_connection import GoogleCalendarConnection
from app.google_calendar.domain.models.calendar_event import CalendarEvent


class IGoogleCalendarConnectionRepository(ABC):
    @abstractmethod
    async def find_by_user_id(self, user_id: str) -> GoogleCalendarConnection | None: ...

    @abstractmethod
    async def save(self, connection: GoogleCalendarConnection) -> GoogleCalendarConnection: ...

    @abstractmethod
    async def delete_by_user_id(self, user_id: str) -> None: ...

    @abstractmethod
    async def find_active_user_ids(self, active_since: datetime) -> list[str]:
        """백그라운드 주기 sync 대상 — needs_reauth=false 이고 active_since 이후
        실제 캘린더 조회가 있었던(last_active_at) 사용자 id 목록."""
        ...

    @abstractmethod
    async def touch_last_active(self, user_id: str, now: datetime) -> None:
        """사용자가 캘린더 데이터를 조회한 시각 기록(요청 경로 전용). 백그라운드
        sync 는 호출하지 않는다 — 그러면 모든 사용자가 영구 활성으로 남는다."""
        ...


class ICalendarEventRepository(ABC):
    @abstractmethod
    async def find_by_date_range(
        self, user_id: str, from_date: str, to_date: str
    ) -> list[CalendarEvent]: ...

    @abstractmethod
    async def upsert_many(self, events: list[CalendarEvent]) -> None: ...

    @abstractmethod
    async def delete_by_google_ids(
        self, user_id: str, google_event_ids: list[str]
    ) -> None: ...

    @abstractmethod
    async def delete_all_by_user(self, user_id: str) -> None: ...
