"""행동 학습 — 사용자 한 명의 기록(이벤트)과 거기서 계산한 통계(모델).

여러 사용자 데이터를 섞지 않는다. 모델은 이벤트에서 언제든 다시 계산할 수 있는 캐시다.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

BehaviorEventType = Literal[
    "sugg_shown",  # 추천이 처음 보임 {suggestion_id, kind, day, ctx}
    "sugg_hidden",  # 보였던 추천을 이번엔 안 냄(순위에서 숨김·후보에서 빠짐) — '무시' 벌점 제외
    "sugg_applied",  # {suggestion_id, kind, action, todo_id, day, ctx, hour?}
    "sugg_dismissed",  # {suggestion_id, kind, reason?, day, ctx}
    "sugg_undone",  # {suggestion_id, kind, day, ctx}
    "todo_moved",  # 날짜를 옮김 {from, to, tag}
    "todo_retimed",  # 시간을 정함·옮김 {hour, minutes?, tag}
    "todo_done",  # 끝냄 {hour, minutes?, tag, day}
]

DismissReason = Literal["not_now", "not_needed", "wrong_time"]
DISMISS_REASONS: tuple[str, ...] = ("not_now", "not_needed", "wrong_time")

# 이 건수(추천에 대한 반응)가 쌓이기 전에는 추천 순서·노출을 바꾸지 않는다.
MIN_EVENTS_TO_RANK = 20
EVENT_RETENTION_DAYS = 180  # 반감기 30일 × 6 — 이보다 오래된 기록은 무게가 2% 아래
HALF_LIFE_DAYS = 30.0


@dataclass(frozen=True)
class BehaviorEvent:
    type: BehaviorEventType
    created_at: datetime
    todo_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Arm:
    """받아들일 확률 Beta(α, β) 의 증거 부분(사전값 제외). 감쇠 가중치로 더한다."""

    pos: float = 0.0
    neg: float = 0.0

    def to_json(self) -> list[float]:
        return [round(self.pos, 4), round(self.neg, 4)]

    @classmethod
    def from_json(cls, v: list[float]) -> "Arm":
        return cls(float(v[0]), float(v[1]))


@dataclass
class BehaviorModel:
    """이벤트에서 계산한 통계 — `ai_user_models.model` 에 JSON 으로 캐시한다.

    - accept: "kind" 와 "kind|wk|dp"(평일·주말 × 오전·오후·저녁) 별 받아들임 증거.
    - actions: 종류별로 실제 누른 버튼(code) 가중치 — 버튼 순서.
    - hours: 태그("*" = 전체)별 24시간 가중치 — 할 일을 하는 시간대.
    - minutes: 태그("*" = 전체)별 걸린 시간(분) 목록 — 길이 추정(중앙값).
    - deferrals: 할 일 id 별 최근 30일 뒤로 미룬 횟수.
    - reactions: 추천에 대한 반응 수(보임 제외, 무게 없이) — MIN_EVENTS_TO_RANK 와 비교.
    """

    accept: dict[str, Arm] = field(default_factory=dict)
    actions: dict[str, dict[str, float]] = field(default_factory=dict)
    hours: dict[str, list[float]] = field(default_factory=dict)
    minutes: dict[str, list[int]] = field(default_factory=dict)
    deferrals: dict[str, int] = field(default_factory=dict)
    reactions: int = 0

    @property
    def can_rank(self) -> bool:
        return self.reactions >= MIN_EVENTS_TO_RANK

    def to_json(self) -> dict[str, Any]:
        return {
            "accept": {k: a.to_json() for k, a in self.accept.items()},
            "actions": self.actions,
            "hours": {k: [round(x, 4) for x in v] for k, v in self.hours.items()},
            "minutes": self.minutes,
            "deferrals": self.deferrals,
            "reactions": self.reactions,
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "BehaviorModel":
        return cls(
            accept={k: Arm.from_json(v) for k, v in (d.get("accept") or {}).items()},
            actions={k: dict(v) for k, v in (d.get("actions") or {}).items()},
            hours={k: list(v) for k, v in (d.get("hours") or {}).items()},
            minutes={k: list(v) for k, v in (d.get("minutes") or {}).items()},
            deferrals=dict(d.get("deferrals") or {}),
            reactions=int(d.get("reactions") or 0),
        )


@dataclass(frozen=True)
class LearningMetrics:
    """최근 30일 추천 효과 — `GET /ai/usage` 의 learning."""

    enabled: bool
    ready: bool  # 순서·노출에 학습을 쓰기 시작했는지
    shown: int
    applied: int
    dismissed: int
    undone: int
    done_after_apply: int  # 적용한 그날 끝낸 수
