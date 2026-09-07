from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.todo.domain.models.todo import RecurrenceRule, Todo
from app.todo.domain.repositories.repository import TagCount, WeeklyTrendDay


class RecurrenceRuleResponse(BaseModel):
    unit: Literal["day", "week"]
    interval: int
    until: str | None

    @classmethod
    def from_domain(cls, rule: RecurrenceRule) -> "RecurrenceRuleResponse":
        return cls(unit=rule.unit, interval=rule.interval, until=rule.until)


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
    # 반복 Todo 필드
    is_virtual: bool
    series_id: str | None
    original_date_key: str | None
    recurrence_rule: RecurrenceRuleResponse | None
    tags: list[str]
    due_date_key: str | None

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
            is_virtual="::" in todo.id,
            series_id=todo.series_id,
            original_date_key=todo.original_date_key,
            recurrence_rule=(
                RecurrenceRuleResponse.from_domain(todo.recurrence_rule)
                if todo.recurrence_rule
                else None
            ),
            tags=todo.tags,
            due_date_key=todo.due_date_key,
        )


class WeeklyTrendDayResponse(BaseModel):
    date_key: str
    done_count: int

    @classmethod
    def from_domain(cls, d: WeeklyTrendDay) -> "WeeklyTrendDayResponse":
        return cls(date_key=d.date_key, done_count=d.done_count)


class TagCountResponse(BaseModel):
    tag: str
    count: int

    @classmethod
    def from_domain(cls, t: TagCount) -> "TagCountResponse":
        return cls(tag=t.tag, count=t.count)


class TodoStatsResponse(BaseModel):
    range: str
    total: int
    done_count: int
    in_progress_count: int
    not_start_count: int
    completion_rate: int
    weekly_trend: list[WeeklyTrendDayResponse]
    tag_distribution: list[TagCountResponse]
    retro_count: int


class TagSearchResponse(BaseModel):
    tags: list[str]
