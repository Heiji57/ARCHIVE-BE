"""이벤트 → 행동 통계(BehaviorModel). 순수 함수 — 같은 이벤트면 같은 모델.

무게는 30일 반감기(`0.5 ** (경과일 / 30)`) — 생활 패턴이 바뀌면 따라간다.

| 이벤트 | 받아들임(A) 에 더하는 것 |
|---|---|
| 적용 | pos +1 |
| 적용하고 그날 끝냄 | pos +1 더(합 +2) |
| 되돌림 | pos −1, neg +1 |
| 넘김 | neg +0.5 (이유: 필요 없음 1, 지금 아님·시간이 안 맞음 0.25) |
| 보였는데 그날 아무 반응 없음 | neg +0.1 — 추천마다 한 번, 마지막이 숨김이면 빼고 |

시간대(B)는 끝낸 시각(무게 1)과 시작 시각을 정하거나 옮긴 것(무게 2 — 빈 칸 추천을 적용한
것도 할 일 수정이라 여기로 들어온다).
길이(C)는 시간 있는 할 일을 끝냈거나 시간을 정했을 때의 길이(분). 미룸(D)은 최근 30일 사용자가
직접 날짜를 뒤로 옮긴 횟수 — 추천·제안 적용으로 옮긴 것(`source`)은 앱이 권한 대로 한 것이라 빼고,
되돌린 적용의 기록은 되돌릴 때 지워진다.
"""

from datetime import date, datetime

from app.ai.domain.models.learning import (
    HALF_LIFE_DAYS,
    Arm,
    BehaviorEvent,
    BehaviorModel,
    LearningMetrics,
)

_DISMISS_WEIGHT = {"not_needed": 1.0, "not_now": 0.25, "wrong_time": 0.25}
_DEFAULT_DISMISS_WEIGHT = 0.5
_IGNORED_WEIGHT = 0.1
_RETIMED_HOUR_WEIGHT = 2.0
_DEFER_WINDOW_DAYS = 30
_MAX_MINUTES_SAMPLES = 50


def weight(at: datetime, now: datetime) -> float:
    age_days = max((now - at).total_seconds() / 86400, 0.0)
    return float(0.5 ** (age_days / HALF_LIFE_DAYS))


def arm_keys(kind: str, ctx: dict[str, str] | None) -> list[str]:
    """종류 전체 팔과 상황(평일·주말 × 시간대) 팔."""
    keys = [kind]
    if ctx and ctx.get("wk") and ctx.get("dp"):
        keys.append(f"{kind}|{ctx['wk']}|{ctx['dp']}")
    return keys


def _tags(tag: str | None) -> list[str]:
    return ["*", tag] if tag else ["*"]


def build_model(events: list[BehaviorEvent], now: datetime, today: date) -> BehaviorModel:
    """`today` 는 사용자 tz 오늘 — 그 전날까지 보였는데 반응 없는 추천을 '무시'로 센다."""
    m = BehaviorModel()
    reacted: set[str] = set()
    done_at = _done_times(events)
    # 추천마다 마지막 보임·숨김 — 마지막이 숨김이면 사용자가 볼 수 없었으니 '무시'로 세지 않는다.
    last_seen: dict[str, BehaviorEvent] = {}
    for e in sorted(events, key=lambda x: x.created_at):
        sid = str(e.data.get("suggestion_id"))
        if e.type in ("sugg_applied", "sugg_dismissed"):
            reacted.add(sid)
        elif e.type in ("sugg_shown", "sugg_hidden"):
            last_seen[sid] = e

    def arms(e: BehaviorEvent) -> list[Arm]:
        keys = arm_keys(str(e.data.get("kind")), e.data.get("ctx"))
        return [m.accept.setdefault(k, Arm()) for k in keys]

    def add_hour(tag: str | None, hour: object, w: float) -> None:
        if not isinstance(hour, int) or not 0 <= hour < 24:
            return
        for key in _tags(tag):
            m.hours.setdefault(key, [0.0] * 24)[hour] += w

    def add_minutes(tag: str | None, minutes: object) -> None:
        if not isinstance(minutes, int) or minutes <= 0:
            return
        for key in _tags(tag):
            samples = m.minutes.setdefault(key, [])
            samples.append(minutes)
            del samples[:-_MAX_MINUTES_SAMPLES]

    for e in events:
        w = weight(e.created_at, now)
        d = e.data
        if e.type == "sugg_applied":
            m.reactions += 1
            bonus = w if _done_after(e, done_at) else 0.0
            for arm in arms(e):
                arm.pos += w + bonus
            code = d.get("action")
            if code:
                prefs = m.actions.setdefault(str(d.get("kind")), {})
                prefs[str(code)] = prefs.get(str(code), 0.0) + w
        elif e.type == "sugg_dismissed":
            m.reactions += 1
            penalty = _DISMISS_WEIGHT.get(str(d.get("reason")), _DEFAULT_DISMISS_WEIGHT) * w
            for arm in arms(e):
                arm.neg += penalty
        elif e.type == "sugg_undone":
            m.reactions += 1
            for arm in arms(e):
                arm.pos = max(arm.pos - w, 0.0)
                arm.neg += w
        elif e.type == "todo_done":
            add_hour(d.get("tag"), d.get("hour"), w)
            add_minutes(d.get("tag"), d.get("minutes"))
        elif e.type == "todo_retimed":
            add_hour(d.get("tag"), d.get("hour"), _RETIMED_HOUR_WEIGHT * w)
            add_minutes(d.get("tag"), d.get("minutes"))
        elif e.type == "todo_moved" and e.todo_id and not d.get("source"):
            recent = (now - e.created_at).days < _DEFER_WINDOW_DAYS
            if recent and str(d.get("to", "")) > str(d.get("from", "")):
                m.deferrals[e.todo_id] = m.deferrals.get(e.todo_id, 0) + 1
    for sid, e in last_seen.items():
        day = e.data.get("day")
        if e.type == "sugg_shown" and sid not in reacted and day and str(day) < today.isoformat():
            for arm in arms(e):
                arm.neg += _IGNORED_WEIGHT * weight(e.created_at, now)
    return m


def _done_times(events: list[BehaviorEvent]) -> dict[tuple[str, str], list[datetime]]:
    """(할 일 id, 사용자 tz 날짜) → 끝낸 시각들."""
    out: dict[tuple[str, str], list[datetime]] = {}
    for e in events:
        if e.type == "todo_done" and e.todo_id and e.data.get("day"):
            out.setdefault((e.todo_id, str(e.data["day"])), []).append(e.created_at)
    return out


def _done_after(applied: BehaviorEvent, done_at: dict[tuple[str, str], list[datetime]]) -> bool:
    """적용 **뒤에** 그날 끝냈는지. '끝냄으로'(mark_done) 적용은 적용하면서 끝내므로(같은 요청에서
    끝냄 기록이 먼저 남는다) 세지 않는다 — 적용 자체가 보상이다."""
    key = (str(applied.data.get("todo_id")), str(applied.data.get("day")))
    return any(t > applied.created_at for t in done_at.get(key, []))


def learning_metrics(
    events: list[BehaviorEvent], enabled: bool, ready: bool
) -> LearningMetrics:
    """주어진 기간(호출부가 30일로 자름)의 반응 수. 적용 후 그날 끝냄은 할 일·날짜로 맞춘다."""
    done_at = _done_times(events)
    count = {t: 0 for t in ("sugg_applied", "sugg_dismissed", "sugg_undone")}
    shown: set[str] = set()  # 숨겼다 다시 보이면 sugg_shown 이 또 남는다 — 추천 수로 센다
    done_after = 0
    for e in events:
        if e.type == "sugg_shown":
            shown.add(str(e.data.get("suggestion_id")))
        elif e.type in count:
            count[e.type] += 1
        if e.type == "sugg_applied" and _done_after(e, done_at):
            done_after += 1
    return LearningMetrics(
        enabled=enabled,
        ready=ready,
        shown=len(shown),
        applied=count["sugg_applied"],
        dismissed=count["sugg_dismissed"],
        undone=count["sugg_undone"],
        done_after_apply=done_after,
    )
