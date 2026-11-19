from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from app.shared.domain.models.base import BaseEntity

AnswerLength = Literal["short", "normal", "detail"]
SOURCES = ("calendar", "todo", "retro", "github")
RETENTION_DAYS = (0, 30, 90, 365)  # 0 = 보관 안 함(하루 지나면 지움)
MAX_MEMORIES = 50
MAX_MEMORY_LEN = 200
MAX_SCHEDULES = 20


@dataclass(kw_only=True)
class AiSettings:
    """AI 비서 시트(L0~L6). 설정 응답을 무겁게 하지 않으려고 `user_settings` 와 따로 둔다."""

    user_id: str
    pet_enabled: bool = True  # L0 빗금이
    tools: dict[str, bool] = field(default_factory=lambda: {s: True for s in SOURCES})  # L1
    confirm_mode: Literal["always"] = "always"  # L5 — 1차는 항상 확인(자동 적용은 2차)
    answer_length: AnswerLength = "normal"  # L2
    deep_search: bool = False  # L2
    memory_enabled: bool = True  # L3
    retention_days: int = 90  # L6

    def enabled_sources(self) -> frozenset[str]:
        return frozenset(s for s in SOURCES if self.tools.get(s, True))

    @classmethod
    def default(cls, user_id: str) -> "AiSettings":
        return cls(user_id=user_id)


@dataclass(kw_only=True)
class AiMemory(BaseEntity):
    """사용자가 알려 둔 것 — 대화마다 프롬프트 앞에 싣는다. 모델이 스스로 만들지는 않는다(1차)."""

    user_id: str
    text: str


@dataclass(kw_only=True)
class AiSchedule(BaseEntity):
    """예약한 일 — 정한 시각(사용자 tz)에 프롬프트로 대화를 한 차례 돌리고 결과를 알림으로."""

    user_id: str
    prompt: str
    # {unit: "day"|"week", weekdays?: [0(일)~6(토)], at: "HH:mm"}
    repeat: dict[str, Any]
    enabled: bool = True
    last_run_date: date | None = None
