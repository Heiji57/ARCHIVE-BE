from datetime import datetime

from pydantic import BaseModel, Field

from app.google_calendar.application.use_cases.get_connection_status import (
    CalendarConnectionStatus,
)
from app.google_calendar.domain.models.calendar_event import CalendarEvent


class CalendarConnectionResponse(BaseModel):
    connected: bool
    needs_reauth: bool = Field(serialization_alias="needsReauth")
    google_user_id: str | None = Field(default=None, serialization_alias="googleUserId")
    last_synced_at: datetime | None = Field(
        default=None, serialization_alias="lastSyncedAt"
    )

    model_config = {"populate_by_name": True}

    @classmethod
    def from_status(cls, status: CalendarConnectionStatus) -> "CalendarConnectionResponse":
        return cls(
            connected=status.connected,
            needs_reauth=status.needs_reauth,
            google_user_id=status.google_user_id,
            last_synced_at=status.last_synced_at,
        )


class CalendarConnectInitResponse(BaseModel):
    authorize_url: str = Field(serialization_alias="authorizeUrl")

    model_config = {"populate_by_name": True}


class CalendarEventResponse(BaseModel):
    """캘린더 이벤트 응답. todo 와 같은 시간 표현(start/end/timezone)을 따른다.

    source 는 항상 'google_calendar' — FE 가 todo 와 구분해 read-only 로 렌더.
    """
    id: str
    title: str
    description: str | None = None
    location: str | None = None
    start_at: datetime | None = Field(default=None, serialization_alias="startAt")
    end_at: datetime | None = Field(default=None, serialization_alias="endAt")
    all_day: bool = Field(serialization_alias="allDay")
    date_key: str = Field(serialization_alias="dateKey")
    timezone: str | None = None
    status: str
    html_link: str | None = Field(default=None, serialization_alias="htmlLink")
    source: str = "google_calendar"

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, event: CalendarEvent) -> "CalendarEventResponse":
        return cls(
            id=event.id,
            title=event.title,
            description=event.description,
            location=event.location,
            start_at=event.start_at,
            end_at=event.end_at,
            all_day=event.all_day,
            date_key=event.date_key,
            timezone=event.timezone,
            status=event.status,
            html_link=event.html_link,
        )
