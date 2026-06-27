from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.google_calendar.domain.models.calendar_event import CalendarEvent
from app.google_calendar.domain.repositories.repository import ICalendarEventRepository
from app.google_calendar.infrastructure.persistence.models.calendar_event_model import (
    CalendarEventModel,
)


class CalendarEventRepository(ICalendarEventRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_date_range(
        self, user_id: str, from_date: str, to_date: str
    ) -> list[CalendarEvent]:
        result = await self._session.execute(
            select(CalendarEventModel)
            .where(
                CalendarEventModel.user_id == user_id,
                CalendarEventModel.date_key >= from_date,
                CalendarEventModel.date_key <= to_date,
                CalendarEventModel.status != "cancelled",
            )
            .order_by(CalendarEventModel.date_key, CalendarEventModel.start_at)
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def upsert_many(self, events: list[CalendarEvent]) -> None:
        """(user_id, google_event_id) 유니크 기준 upsert.

        merge 는 PK(id) 기준이라 같은 google_event_id 가 새 id 로 들어오면 유니크
        충돌이 난다. PostgreSQL ON CONFLICT 로 기존 행의 id/created_at 은 보존하고
        가변 필드만 갱신한다.
        """
        if not events:
            return
        for event in events:
            values = {
                "id": event.id,
                "user_id": event.user_id,
                "connection_id": event.connection_id,
                "google_event_id": event.google_event_id,
                "calendar_id": event.calendar_id,
                "title": event.title,
                "description": event.description,
                "location": event.location,
                "start_at": event.start_at,
                "end_at": event.end_at,
                "all_day": event.all_day,
                "date_key": event.date_key,
                "timezone": event.timezone,
                "status": event.status,
                "html_link": event.html_link,
                "created_at": event.created_at,
                "updated_at": event.updated_at,
            }
            stmt = pg_insert(CalendarEventModel).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_id", "google_event_id"],
                set_={
                    "calendar_id": stmt.excluded.calendar_id,
                    "title": stmt.excluded.title,
                    "description": stmt.excluded.description,
                    "location": stmt.excluded.location,
                    "start_at": stmt.excluded.start_at,
                    "end_at": stmt.excluded.end_at,
                    "all_day": stmt.excluded.all_day,
                    "date_key": stmt.excluded.date_key,
                    "timezone": stmt.excluded.timezone,
                    "status": stmt.excluded.status,
                    "html_link": stmt.excluded.html_link,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await self._session.execute(stmt)
        await self._session.flush()

    async def delete_by_google_ids(
        self, user_id: str, google_event_ids: list[str]
    ) -> None:
        if not google_event_ids:
            return
        await self._session.execute(
            delete(CalendarEventModel).where(
                CalendarEventModel.user_id == user_id,
                CalendarEventModel.google_event_id.in_(google_event_ids),
            )
        )

    async def delete_all_by_user(self, user_id: str) -> None:
        await self._session.execute(
            delete(CalendarEventModel).where(CalendarEventModel.user_id == user_id)
        )

    def _to_entity(self, model: CalendarEventModel) -> CalendarEvent:
        return CalendarEvent(
            id=model.id,
            user_id=model.user_id,
            connection_id=model.connection_id,
            google_event_id=model.google_event_id,
            calendar_id=model.calendar_id,
            title=model.title,
            description=model.description,
            location=model.location,
            start_at=model.start_at,
            end_at=model.end_at,
            all_day=model.all_day,
            date_key=model.date_key,
            timezone=model.timezone,
            status=model.status,
            html_link=model.html_link,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
