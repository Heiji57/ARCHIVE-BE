from abc import ABC, abstractmethod

from app.google_calendar.domain.models.calendar_connection import GoogleCalendarConnection
from app.google_calendar.domain.models.calendar_event import CalendarEvent


class IGoogleCalendarConnectionRepository(ABC):
    @abstractmethod
    async def find_by_user_id(self, user_id: str) -> GoogleCalendarConnection | None: ...

    @abstractmethod
    async def save(self, connection: GoogleCalendarConnection) -> GoogleCalendarConnection: ...

    @abstractmethod
    async def delete_by_user_id(self, user_id: str) -> None: ...


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
