import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

from app.shared.domain.utils.timezone import validate_timezone
from app.todo.domain.models.todo import RecurrenceRule

_TAG_MAX_LEN = 20
_TAGS_MAX_COUNT = 10


_VALID_STATUSES = {"not-start", "in-progress", "done"}
_DATE_KEY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_VALID_SCOPES = {"this", "following", "all"}


def _validate_tags(v: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for tag in v:
        if len(tag) < 1 or len(tag) > _TAG_MAX_LEN:
            raise ValueError(f"each tag must be between 1 and {_TAG_MAX_LEN} characters")
        if tag not in seen:
            seen.add(tag)
            deduped.append(tag)
    if len(deduped) > _TAGS_MAX_COUNT:
        raise ValueError(f"tags must have at most {_TAGS_MAX_COUNT} items")
    return deduped


class RecurrenceRuleRequest(BaseModel):
    unit: Literal["day", "week", "month", "year"]
    interval: int
    until: str | None = None
    # unit=week 전용 — 0=월 … 6=일, 1~7개·중복 없음. 생략/null = 시작일 요일.
    weekdays: list[int] | None = None
    # unit=month 전용·필수 — 1~4 = n번째, -1 = 마지막 (요일은 시작일 요일).
    month_week: Literal[1, 2, 3, 4, -1] | None = None

    @field_validator("interval")
    @classmethod
    def interval_range(cls, v: int) -> int:
        if not (1 <= v <= 365):
            raise ValueError("interval must be between 1 and 365")
        return v

    @field_validator("until")
    @classmethod
    def until_format(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError("until must be in YYYY-MM-DD format")
        return v

    @field_validator("weekdays")
    @classmethod
    def weekdays_values(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return v
        if not v:
            raise ValueError("weekdays must not be empty")
        if any(not (0 <= d <= 6) for d in v):
            raise ValueError("weekdays items must be between 0 and 6")
        if len(set(v)) != len(v):
            raise ValueError("weekdays must not contain duplicates")
        return sorted(v)

    @model_validator(mode="after")
    def unit_specific_fields(self) -> "RecurrenceRuleRequest":
        if self.weekdays is not None and self.unit != "week":
            raise ValueError("weekdays is only allowed when unit is 'week'")
        if self.unit == "month" and self.month_week is None:
            raise ValueError("month_week is required when unit is 'month'")
        if self.month_week is not None and self.unit != "month":
            raise ValueError("month_week is only allowed when unit is 'month'")
        return self

    def to_domain(self) -> RecurrenceRule:
        return RecurrenceRule(
            unit=self.unit,
            interval=self.interval,
            until=self.until,
            weekdays=tuple(self.weekdays) if self.weekdays is not None else None,
            month_week=self.month_week,
        )


class TodoCreateRequest(BaseModel):
    title: str
    date_key: str
    description: str = ""
    status: str = "not-start"
    start_time: datetime | None = None
    end_time: datetime | None = None
    timezone: str | None = None
    # None → user_settings.calendar_auto_push_todo 기본값. True/False → 개별 지정.
    push_to_calendar: bool | None = None
    recurrence_rule: RecurrenceRuleRequest | None = None
    tags: list[str] = []
    due_date_key: str | None = None

    @field_validator("tags")
    @classmethod
    def tags_valid(cls, v: list[str]) -> list[str]:
        return _validate_tags(v)

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        if v not in _VALID_STATUSES:
            raise ValueError(f"status must be one of {_VALID_STATUSES}")
        return v

    @field_validator("date_key")
    @classmethod
    def date_key_format(cls, v: str) -> str:
        if not _DATE_KEY_RE.fullmatch(v):
            raise ValueError("date_key must be in YYYY-MM-DD format")
        return v

    @field_validator("due_date_key")
    @classmethod
    def due_date_key_format(cls, v: str | None) -> str | None:
        if v is not None and not _DATE_KEY_RE.fullmatch(v):
            raise ValueError("due_date_key must be in YYYY-MM-DD format")
        return v

    @field_validator("timezone")
    @classmethod
    def timezone_valid(cls, v: str | None) -> str | None:
        if v is not None and not validate_timezone(v):
            raise ValueError(f"Invalid IANA timezone: {v}")
        return v

    @model_validator(mode="after")
    def validate_time_fields(self) -> "TodoCreateRequest":
        has_time = self.start_time is not None or self.end_time is not None
        if has_time and self.timezone is None:
            raise ValueError("timezone is required when start_time or end_time is provided")
        if self.due_date_key is not None and self.due_date_key < self.date_key:
            raise ValueError("due_date_key must be >= date_key")
        return self


class TodoUpdateRequest(BaseModel):
    title: str | None = None
    status: str | None = None
    description: str | None = None
    date_key: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    timezone: str | None = None
    recurrence_scope: str = "this"
    recurrence_rule: RecurrenceRuleRequest | None = None
    tags: list[str] | None = None
    due_date_key: str | None = None

    @field_validator("tags")
    @classmethod
    def tags_valid_update(cls, v: list[str] | None) -> list[str] | None:
        return _validate_tags(v) if v is not None else v

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_STATUSES:
            raise ValueError(f"status must be one of {_VALID_STATUSES}")
        return v

    @field_validator("date_key")
    @classmethod
    def date_key_format(cls, v: str | None) -> str | None:
        if v is not None and not _DATE_KEY_RE.fullmatch(v):
            raise ValueError("date_key must be in YYYY-MM-DD format")
        return v

    @field_validator("timezone")
    @classmethod
    def timezone_valid(cls, v: str | None) -> str | None:
        if v is not None and not validate_timezone(v):
            raise ValueError(f"Invalid IANA timezone: {v}")
        return v

    @field_validator("recurrence_scope")
    @classmethod
    def scope_valid(cls, v: str) -> str:
        if v not in _VALID_SCOPES:
            raise ValueError(f"recurrenceScope must be one of {_VALID_SCOPES}")
        return v

    @field_validator("due_date_key")
    @classmethod
    def due_date_key_format(cls, v: str | None) -> str | None:
        if v is not None and not _DATE_KEY_RE.fullmatch(v):
            raise ValueError("due_date_key must be in YYYY-MM-DD format")
        return v

    @model_validator(mode="after")
    def validate_time_fields(self) -> "TodoUpdateRequest":
        provided = self.model_fields_set
        start_setting = "start_time" in provided and self.start_time is not None
        end_setting = "end_time" in provided and self.end_time is not None
        if (start_setting or end_setting) and ("timezone" not in provided or self.timezone is None):
            raise ValueError("timezone is required when start_time or end_time is set")
        if "due_date_key" in provided and self.due_date_key is not None:
            # date_key 가 요청에 함께 포함된 경우만 Presentation 레벨에서 체크
            # (date_key 미포함 시 use-case _apply_patch 에서 DB 기존값과 비교)
            if self.date_key is not None and self.due_date_key < self.date_key:
                raise ValueError("due_date_key must be >= date_key")
        return self
