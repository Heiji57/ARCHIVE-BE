import re
from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator

from app.shared.domain.utils.timezone import validate_timezone


_VALID_STATUSES = {"not-start", "in-progress", "done"}
_DATE_KEY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


class TodoCreateRequest(BaseModel):
    title: str
    date_key: str
    description: str = ""
    status: str = "not-start"
    start_time: datetime | None = None
    end_time: datetime | None = None
    timezone: str | None = None

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
