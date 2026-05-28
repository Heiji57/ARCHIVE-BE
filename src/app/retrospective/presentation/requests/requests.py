import re

from pydantic import BaseModel, field_validator

_VALID_RETRO_TYPES = {"daily", "weekly", "monthly", "yearly"}
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


class EntryCreateRequest(BaseModel):
    date_key: str
    title: str
    content: str = ""
    retro_type: str = "daily"

    @field_validator("retro_type")
    @classmethod
    def retro_type_must_be_valid(cls, v: str) -> str:
        if v not in _VALID_RETRO_TYPES:
            raise ValueError(f"retro_type must be one of {_VALID_RETRO_TYPES}")
        return v

    @field_validator("date_key")
    @classmethod
    def date_key_format(cls, v: str) -> str:
        if not _DATE_RE.fullmatch(v):
            raise ValueError("date_key must be in YYYY-MM-DD format")
        return v


class EntryUpsertRequest(BaseModel):
    date_key: str
    title: str
    content: str = ""
    retro_type: str = "daily"

    @field_validator("retro_type")
    @classmethod
    def retro_type_must_be_valid(cls, v: str) -> str:
        if v not in _VALID_RETRO_TYPES:
            raise ValueError(f"retro_type must be one of {_VALID_RETRO_TYPES}")
        return v

    @field_validator("date_key")
    @classmethod
    def date_key_format(cls, v: str) -> str:
        if not _DATE_RE.fullmatch(v):
            raise ValueError("date_key must be in YYYY-MM-DD format")
        return v
