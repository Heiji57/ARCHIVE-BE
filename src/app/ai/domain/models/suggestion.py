from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from app.ai.domain.models.learning import LearningMetrics
from app.shared.domain.models.base import BaseEntity

SuggestionKind = Literal["overdue", "free_slot", "unscheduled_long", "commit_match"]
SuggestionStatus = Literal["shown", "applied", "dismissed"]


@dataclass(frozen=True)
class SuggestionAction:
    label: str
    # PATCH /todos/{id} 본문과 같은 모양(snake_case) — 적용은 할 일 묶음 수정 규칙을 그대로 탄다.
    # "drop"(내려놓기)만 예외로 patch 가 비어 있고 할 일을 휴지통으로 보낸다(되돌리면 되살림).
    patch: dict[str, Any]
    # 버튼 종류 — to_today | to_tomorrow | drop | schedule | mark_done. 학습이 "어떤 버튼을
    # 눌렀나" 를 세는 열쇠(순서가 바뀌어도 같은 버튼).
    code: str = ""


@dataclass(frozen=True)
class SuggestionCandidate:
    """규칙이 만든 추천 하나(아직 저장 전). (kind, todo_id) 가 그날의 정체성이다."""

    kind: SuggestionKind
    todo_id: str
    title: str
    reason: str
    actions: tuple[SuggestionAction, ...]
    slot: tuple[datetime, datetime] | None = None  # 캘린더 흐린 칸
    # 이유 종류 — overdue | overdue_deferred | free_slot | free_slot_usual_time |
    # free_slot_usual_length | commit_match. FE 가 문장 대신 아이콘·문구를 고를 때 쓴다.
    reason_code: str = ""
    urgency: float = 1.0  # 순위 가중치(지난 마감은 오래될수록 큼)
    learned: bool = False  # 학습한 값이 순서·시각·길이·문구에 쓰였는지
    tag: str | None = None  # 학습 기록용(할 일의 첫 태그)


@dataclass(kw_only=True)
class Suggestion(BaseEntity):
    """저장된 추천. 같은 날 같은 (kind, todo_id) 는 한 행.

    넘긴(dismissed) 추천은 다시 안 나온다.
    """

    user_id: str
    date_key: str
    kind: SuggestionKind
    todo_id: str
    payload: dict[str, Any] = field(default_factory=dict)  # title, reason, slot, actions
    status: SuggestionStatus = "shown"
    # 적용 결과 — 되돌리기용 {"todo_id": 적용된 할 일 id, "previous": 바뀐 필드의 이전 값}
    applied: dict[str, Any] | None = None

    @property
    def actions(self) -> list[SuggestionAction]:
        return [
            SuggestionAction(a["label"], a["patch"], a.get("code", ""))
            for a in self.payload.get("actions", [])
        ]


@dataclass(frozen=True)
class AiUsageReport:
    day_used: int
    day_limit: int
    month_used: int
    month_limit: int
    learning: LearningMetrics | None = None  # 최근 30일 추천 효과(행동 학습)
