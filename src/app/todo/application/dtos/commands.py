from dataclasses import dataclass, field
from datetime import datetime

# 부분 수정 sentinel 은 공용 하나 — 모듈마다 클래스가 다르면 isinstance 판정이 어긋난다.
from app.shared.domain.utils.unset import UNSET as UNSET
from app.shared.domain.utils.unset import _Unset as _Unset
from app.todo.domain.models.todo import RecurrenceRule


@dataclass(frozen=True)
class CreateTodoCommand:
    user_id: str
    title: str
    date_key: str
    description: str = ""
    status: str = "not-start"
    start_time: datetime | None = None
    end_time: datetime | None = None
    timezone: str | None = None
    # None → user_settings.calendar_auto_push_todo 기본값 적용.
    # True/False → 사이드바에서 개별 지정(기본값 override).
    push_to_calendar: bool | None = None
    recurrence_rule: RecurrenceRule | None = None
    tags: list[str] = field(default_factory=list)
    due_date_key: str | None = None
    calendar_id: str | None = None  # None = 기본 캘린더


@dataclass(frozen=True)
class UpdateTodoCommand:
    id: str
    user_id: str
    title: str | None = None
    status: str | None = None
    description: str | None = None
    date_key: str | None = None
    # 시간 필드는 sentinel — UNSET(미전송) vs None(명시 clear) 구분
    start_time: datetime | None | _Unset = UNSET
    end_time: datetime | None | _Unset = UNSET
    timezone: str | None | _Unset = UNSET
    # 반복 Todo 편집 범위: "this" | "following" | "all"
    recurrence_scope: str = "this"
    recurrence_rule: RecurrenceRule | None = None
    tags: list[str] | _Unset = UNSET
    due_date_key: str | None | _Unset = UNSET
    # None = 기본 캘린더로 옮김, UNSET = 그대로
    calendar_id: str | None | _Unset = UNSET
