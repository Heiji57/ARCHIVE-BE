from typing import Literal

from pydantic import BaseModel, Field, field_validator

PaletteKey = Literal["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"]


def _clean_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("name must not be blank")
    return v


class CreateCalendarRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    color: PaletteKey = "c1"

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return _clean_name(v)


class UpdateCalendarRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    color: PaletteKey | None = None
    sort_order: int | None = Field(default=None, ge=0, alias="sortOrder")
    push_to_google: bool | None = Field(default=None, alias="pushToGoogle")

    model_config = {"populate_by_name": True}

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return None if v is None else _clean_name(v)
