"""학습한 통계로 추천을 고른다 — 규칙이 만든 후보의 순서·노출, 빈 칸 시각·길이, 버튼 순서.

- 받아들일 확률(A): 톰슨 샘플링. 종류 팔의 평균을 사전값(무게 2)으로 둔 상황 팔
  Beta(α, β) 에서 하나 뽑는다. 뽑은 값이 `HIDE_BELOW` 보다 작으면 이번엔 숨긴다 — 자주 넘긴
  종류도 가끔 다시 보여(탐색) "한 번 넘기면 영원히 안 나옴" 을 막는다. 씨앗은 (사용자, 날짜,
  시간대, 종류, 할 일) — 후보마다 따로라, 같은 시간대 안에서는 새로 고치거나 다른 추천을
  누르거나 해도 남은 추천의 뽑힌 값이 흔들리지 않는다.
- 시간대(B): 태그별 24시간 분포를 전체 분포 쪽으로 당긴 것(디리클레, 무게 5). 증거가
  `MIN_HOUR_EVIDENCE` 보다 적으면 쓰지 않는다(앞에서부터 찾기 그대로).
- 길이(C): (n × 중앙값 + 3 × 기본값) / (n + 3) — 태그는 전체 추정 쪽으로 다시 당긴다.
- 데이터가 없거나 학습을 끄면 규칙 그대로(지금까지와 같은 결과).
"""

import hashlib
import random
from dataclasses import replace
from datetime import datetime, timedelta
from statistics import median

from app.ai.domain.models.learning import BehaviorModel
from app.ai.domain.models.suggestion import SuggestionAction, SuggestionCandidate
from app.ai.domain.services.behavior_model import arm_keys

HIDE_BELOW = 0.1
MIN_HOUR_EVIDENCE = 5.0
MIN_LENGTH_SAMPLES = 3
_TAG_PRIOR = 5.0
_CTX_PRIOR = 2.0
_LENGTH_PRIOR = 3
_MIN_MINUTES, _MAX_MINUTES, _STEP = 15, 240, 15
_USUAL_FACTOR = 2.0  # 고른 시간대가 고르게 나눈 값(1/24)의 두 배 이상이면 "평소 하던 시간"


def daypart(hour: int) -> str:
    return "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"


def context_of(local_now: datetime) -> dict[str, str]:
    """추천을 보거나 누른 상황 — 평일·주말 × 오전·오후·저녁(사용자 tz)."""
    return {
        "wk": "weekend" if local_now.weekday() >= 5 else "weekday",
        "dp": daypart(local_now.hour),
    }


def rank_seed(user_id: str, day: str, ctx: dict[str, str]) -> str:
    """같은 날·같은 시간대면 같은 씨앗."""
    return f"{user_id}|{day}|{ctx.get('dp')}"


def _rng(seed: str, c: SuggestionCandidate) -> random.Random:
    digest = hashlib.sha256(f"{seed}|{c.kind}|{c.todo_id}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


# ── A. 받아들일 확률 ──────────────────────────────────────────────────────────


def accept_params(model: BehaviorModel, kind: str, ctx: dict[str, str]) -> tuple[float, float]:
    keys = arm_keys(kind, ctx)
    base = model.accept.get(keys[0])
    a_k = 1.0 + (base.pos if base else 0.0)
    b_k = 1.0 + (base.neg if base else 0.0)
    mean = a_k / (a_k + b_k)
    if len(keys) < 2:
        return a_k, b_k
    arm = model.accept.get(keys[1])
    return (
        _CTX_PRIOR * mean + (arm.pos if arm else 0.0),
        _CTX_PRIOR * (1 - mean) + (arm.neg if arm else 0.0),
    )


def rank(
    candidates: list[SuggestionCandidate],
    model: BehaviorModel,
    ctx: dict[str, str],
    seed: str,
) -> list[SuggestionCandidate]:
    """뽑은 받아들일 확률 × 급함 순. 너무 낮게 뽑힌 것은 이번엔 뺀다. 버튼은 자주 누른 순.

    후보마다 씨앗이 따로라 다른 후보가 빠지거나 늘어도 그 후보의 뽑힌 값은 같다.
    """
    if not model.can_rank:
        return [_order_actions(c, model) for c in candidates]
    scored: list[tuple[float, int, SuggestionCandidate]] = []
    for i, c in enumerate(candidates):
        a, b = accept_params(model, c.kind, ctx)
        theta = _rng(seed, c).betavariate(a, b)
        if theta < HIDE_BELOW:
            continue
        scored.append((theta * c.urgency, i, replace(_order_actions(c, model), learned=True)))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [c for _, _, c in scored]


def _order_actions(c: SuggestionCandidate, model: BehaviorModel) -> SuggestionCandidate:
    """자주 누른 버튼을 앞으로. 미룬 일의 '내려놓기'는 규칙이 정한 맨 앞을 지킨다."""
    prefs = model.actions.get(c.kind)
    if not prefs or len(c.actions) < 2:
        return c
    pinned = [a for a in c.actions if a.code == "drop"]
    rest = [a for a in c.actions if a.code != "drop"]
    order = sorted(range(len(rest)), key=lambda i: (-prefs.get(rest[i].code, 0.0), i))
    actions: tuple[SuggestionAction, ...] = (*pinned, *(rest[i] for i in order))
    return c if actions == c.actions else replace(c, actions=actions)


# ── B. 시간대 ─────────────────────────────────────────────────────────────────


def hour_profile(model: BehaviorModel, tag: str | None) -> tuple[list[float], float] | None:
    """시간대별 확률과 증거량. 증거가 모자라면 None(쓰지 않음)."""
    glob = model.hours.get("*") or [0.0] * 24
    g_total = sum(glob)
    p_glob = [(x + 1.0) / (g_total + 24.0) for x in glob]
    own = model.hours.get(tag) if tag else None
    if own and sum(own) > 0:
        t_total = sum(own)
        probs = [(own[h] + _TAG_PRIOR * p_glob[h]) / (t_total + _TAG_PRIOR) for h in range(24)]
    else:
        probs = p_glob
    # 증거는 전체 기록으로 판단한다(전체 ⊇ 태그). 태그 기록이 몇 건뿐이면 확률이 전체 분포 쪽으로
    # 당겨져 있으니 그대로 쓸 수 있다 — 태그 1건 때문에 학습한 시간대를 꺼 버리지 않게.
    return (probs, g_total) if g_total >= MIN_HOUR_EVIDENCE else None


def slot_score(probs: list[float], start: datetime, end: datetime) -> float:
    """칸이 걸친 시간대 확률의 평균(15분 단위, 사용자 tz 시각)."""
    total, steps, cursor = 0.0, 0, start
    while cursor < end:
        total += probs[cursor.hour]
        steps += 1
        cursor += timedelta(minutes=_STEP)
    return total / steps if steps else 0.0


def is_usual_hour(probs: list[float], hour: int) -> bool:
    return probs[hour] >= _USUAL_FACTOR / 24


# ── C. 길이 ──────────────────────────────────────────────────────────────────


def _shrink(samples: list[int], prior: float) -> float:
    n = len(samples)
    return (n * median(samples) + _LENGTH_PRIOR * prior) / (n + _LENGTH_PRIOR) if n else prior


def _round_minutes(minutes: float, default: int) -> int:
    """15분 단위, 15분~max(240, 기본값) — 사용자가 정한 긴 기본값은 자르지 않는다."""
    rounded = int(round(minutes / _STEP) * _STEP)
    return max(_MIN_MINUTES, min(max(_MAX_MINUTES, default), rounded))


def estimate_minutes(model: BehaviorModel, tag: str | None, default: int) -> tuple[int, bool]:
    """(길이(분), 학습값인지). 학습값이 아니면 기본값을 **그대로** 돌려준다.

    전체 기록이 3건 미만이면 기본값(1~2건으로 칸 길이를 바꾸지 않는다). 태그 기록이 1~2건이어도
    전체 기록이 충분하면 학습값이다(전체 ⊇ 태그). 추정을 15분 단위로 맞춘 값이 기본값을 같은
    단위로 맞춘 값과 같으면 기본값 그대로 — 기본 20분인 사용자에게 "보통 15분" 이라 하지 않게.
    """
    glob = model.minutes.get("*") or []
    if len(glob) < MIN_LENGTH_SAMPLES:
        return default, False
    own = (model.minutes.get(tag) or []) if tag else []
    estimate = _round_minutes(_shrink(own, _shrink(glob, float(default))), default)
    if estimate == _round_minutes(float(default), default):
        return default, False
    return estimate, True
