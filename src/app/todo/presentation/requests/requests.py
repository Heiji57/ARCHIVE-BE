import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

from app.shared.domain.utils.timezone import validate_timezone
from app.todo.domain.models.todo import RecurrenceRule


_VALID_STATUSES = {"not-start", "in-progress", "done"}
_DATE_KEY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_VALID_SCOPES = {"this", "following", "all"}


class RecurrenceRuleRequest(BaseModel):
    unit: Literal["day", "week"]
    interval: int
    until: str | None = None

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

    def to_domain(self) -> RecurrenceRule:
        return RecurrenceRule(unit=self.unit, interval=self.interval, until=self.until)


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
        if self.start_time is not None and self.end_time is not None:
            if self.end_time <= self.start_time:
                raise ValueError("end_time must be later than start_time")
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

    @model_validator(mode="after")
    def validate_time_fields(self) -> "TodoUpdateRequest":
        provided = self.model_fields_set
        start_setting = "start_time" in provided and self.start_time is not None
        end_setting = "end_time" in provided and self.end_time is not None
        if (start_setting or end_setting) and ("timezone" not in provided or self.timezone is None):
            raise ValueError("timezone is required when start_time or end_time is set")
        if "start_time" in provided and "end_time" in provided:
            if self.start_time is not None and self.end_time is not None:
                if self.end_time <= self.start_time:
                    raise ValueError("end_time must be later than start_time")
        return self
