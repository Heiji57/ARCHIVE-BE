from datetime import datetime

from pydantic import BaseModel, Field

from app.calendars.domain.models.calendar import Calendar


class CalendarResponse(BaseModel):
    id: str
    name: str  # 기본 캘린더는 고정 키 "default" — FE 가 locale 로 표시 이름을 정한다
    color: str
    sort_order: int = Field(serialization_alias="sortOrder")
    is_default: bool = Field(serialization_alias="isDefault")
    push_to_google: bool = Field(serialization_alias="pushToGoogle")
    created_at: datetime = Field(serialization_alias="createdAt")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_entity(cls, c: Calendar) -> "CalendarResponse":
        return cls(
            id=c.id,
            name=c.name,
            color=c.color,
            sort_order=c.sort_order,
            is_default=c.is_default,
            push_to_google=c.push_to_google,
            created_at=c.created_at,
        )
