from datetime import datetime

from pydantic import BaseModel

from app.google_calendar.presentation.responses.responses import CalendarEventResponse
from app.todo.domain.models.todo import Todo


class TodoResponse(BaseModel):
    id: str
    user_id: str
    title: str
    status: str
    date_key: str
    description: str
    completed: bool
    start_time: datetime | None
    end_time: datetime | None
    timezone: str | None
    created_at: datetime
    updated_at: datetime | None
    completed_at: datetime | None
    # Google Calendar 연동 상태 — FE 사이드바 '캘린더에 추가/빼기' 버튼 렌더용.
    # calendar_linked: 연동됨(또는 진행/대기 중). calendar_push_status: 세부 상태.
    calendar_linked: bool
    calendar_push_status: str | None

    @classmethod
    def from_entity(cls, todo: Todo) -> "TodoResponse":
        return cls(
            id=todo.id,
            user_id=todo.user_id,
            title=todo.title,
            status=todo.status.value,
            date_key=todo.date_key,
            description=todo.description,
            completed=todo.status.value == "done",
            start_time=todo.start_time,
            end_time=todo.end_time,
            timezone=todo.timezone,
            created_at=todo.created_at,
            updated_at=todo.updated_at,
            completed_at=todo.completed_at,
            calendar_linked=todo.is_calendar_linked,
            calendar_push_status=todo.calendar_push_status,
        )


class TodosWithEventsResponse(BaseModel):
    """GET /todos 응답.

    todos 와 별개로 events(Google Calendar 이벤트)를 함께 반환한다.
    캘린더 미연결 사용자는 events 가 항상 빈 배열. FE 는 같은 날짜/타임라인에
    todos 와 events 를 함께 렌더하되, events 는 read-only(source='google_calendar').
    """
    todos: list[TodoResponse]
    events: list[CalendarEventResponse]
