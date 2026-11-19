import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ApplySuggestionRequest(BaseModel):
    action_index: int = Field(default=0, ge=0, alias="actionIndex")

    model_config = {"populate_by_name": True}


class DismissSuggestionRequest(BaseModel):
    """넘긴 이유(선택) — 학습 무게만 바꾼다. 본문 없이 보내도 된다."""

    reason: Literal["not_now", "not_needed", "wrong_time"] | None = None


class CreateConversationRequest(BaseModel):
    title: str = Field(default="", max_length=60)


def _not_blank(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("must not be blank")
    return v


class PostMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)

    @field_validator("text")
    @classmethod
    def _strip(cls, v: str) -> str:
        return _not_blank(v)

    # FE 화면 맥락(선택한 날짜, 보고 있던 할 일 등) — 서버는 저장만 한다(1차).
    context: dict[str, Any] | None = None


class ApplyProposalRequest(BaseModel):
    """고른 항목만(시안의 넣음/뺌). 생략하면 전부."""

    item_keys: list[str] | None = Field(default=None, alias="itemKeys")

    model_config = {"populate_by_name": True}


_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_SOURCES = {"calendar", "todo", "retro", "github"}


class PatchAiSettingsRequest(BaseModel):
    """`PATCH /ai/settings` — 보낸 필드만. tools 는 보낸 출처만 바뀐다."""

    pet_enabled: bool | None = Field(default=None, alias="petEnabled")
    tools: dict[str, bool] | None = None
    answer_length: Literal["short", "normal", "detail"] | None = Field(
        default=None, alias="answerLength"
    )
    deep_search: bool | None = Field(default=None, alias="deepSearch")
    memory_enabled: bool | None = Field(default=None, alias="memoryEnabled")
    retention_days: Literal[0, 30, 90, 365] | None = Field(default=None, alias="retentionDays")
    learning_enabled: bool | None = Field(default=None, alias="learningEnabled")

    model_config = {"populate_by_name": True}

    @field_validator("tools")
    @classmethod
    def _tools(cls, v: dict[str, bool] | None) -> dict[str, bool] | None:
        if v is not None and set(v) - _SOURCES:
            raise ValueError(f"tools keys must be among {sorted(_SOURCES)}")
        return v

    def provided(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.model_fields_set if getattr(self, k) is not None}


class AddMemoryRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200)

    @field_validator("text")
    @classmethod
    def _strip(cls, v: str) -> str:
        return _not_blank(v)


class ScheduleRepeat(BaseModel):
    unit: Literal["day", "week"]
    weekdays: list[int] | None = None  # 0(일)~6(토), unit=week 일 때 필수
    at: str  # HH:mm (사용자 tz)

    @field_validator("at")
    @classmethod
    def _at(cls, v: str) -> str:
        if not _HHMM.fullmatch(v):
            raise ValueError("at must be HH:mm")
        return v

    @model_validator(mode="after")
    def _weekdays(self) -> "ScheduleRepeat":
        if self.unit == "week":
            days = self.weekdays or []
            if not days or any(d < 0 or d > 6 for d in days) or len(set(days)) != len(days):
                raise ValueError("weekdays must be unique 0(Sun)~6(Sat) for unit=week")
        return self


class CreateScheduleRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)
    repeat: ScheduleRepeat
    enabled: bool = True


class UpdateScheduleRequest(BaseModel):
    prompt: str | None = Field(default=None, min_length=1, max_length=1000)
    repeat: ScheduleRepeat | None = None
    enabled: bool | None = None

    def provided(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k in self.model_fields_set:
            v = getattr(self, k)
            if v is not None:
                out[k] = v.model_dump(exclude_none=True) if isinstance(v, ScheduleRepeat) else v
        return out
