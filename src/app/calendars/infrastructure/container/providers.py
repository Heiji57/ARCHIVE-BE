from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from app.calendars.application.use_cases.calendars import (
    CreateCalendarUseCase,
    DeleteCalendarUseCase,
    ListCalendarsUseCase,
    UpdateCalendarUseCase,
)
from app.calendars.domain.repositories.repository import ICalendarRepository
from app.calendars.infrastructure.persistence.repositories.calendar_repo import (
    CalendarRepository,
)


class CalendarsProvider(Provider):
    """사용자 캘린더 모듈 — 리포지토리와 유스케이스."""

    scope = Scope.REQUEST

    @provide
    def calendar_repo(self, session: AsyncSession) -> ICalendarRepository:
        return CalendarRepository(session)

    list_calendars = provide(ListCalendarsUseCase)
    create_calendar = provide(CreateCalendarUseCase)
    update_calendar = provide(UpdateCalendarUseCase)
    delete_calendar = provide(DeleteCalendarUseCase)
