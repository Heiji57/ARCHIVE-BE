import re

from pydantic import BaseModel, field_validator, model_validator


_VALID_STATUSES = {"not-start", "in-progress", "done"}
_DATE_KEY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TIME_RE = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def _validate_hhmm(v: str | None) -> str | None:
    if v is None:
        return v
    if not _TIME_RE.fullmatch(v):
        raise ValueError('time must be in "HH:mm" 24-hour format')
    return v


def _to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


class TodoCreateRequest(BaseModel):
    title: str
    date_key: str
    description: str = ""
    status: str = "not-start"
    start_time: str | None = None
    end_time: str | None = None

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

    @field_validator("start_time", "end_time")
    @classmethod
    def time_format(cls, v: str | None) -> str | None:
        return _validate_hhmm(v)

    @model_validator(mode="after")
    def end_after_start(self) -> "TodoCreateRequest":
        if self.start_time is not None and self.end_time is not None:
            if _to_minutes(self.end_time) <= _to_minutes(self.start_time):
                raise ValueError("end_time must be later than start_time")
        return self


class TodoUpdateRequest(BaseModel):
    title: str | None = None
    status: str | None = None
    description: str | None = None
    date_key: str | None = None
    start_time: str | None = None
    end_time: str | None = None

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

    @field_validator("start_time", "end_time")
    @classmethod
    def time_format(cls, v: str | None) -> str | None:
        return _validate_hhmm(v)

    @model_validator(mode="after")
    def end_after_start(self) -> "TodoUpdateRequest":
        # 양쪽 모두 명시적으로 들어왔고 둘 다 None 이 아닐 때만 교차 검증
        provided = self.model_fields_set
        if "start_time" in provided and "end_time" in provided:
            if self.start_time is not None and self.end_time is not None:
                if _to_minutes(self.end_time) <= _to_minutes(self.start_time):
                    raise ValueError("end_time must be later than start_time")
        return self
