"""규칙 기반 추천 — LLM 없이 만든다(비용 0, 결정적). 이유 문장도 템플릿.

| 종류 | 규칙 | 행동 |
|---|---|---|
| overdue | 끝내지 않았고 마감(due, 없으면 date)이 오늘 이전 | 오늘로 / 내일로 |
| free_slot | 오늘의 시간 없는 할 일 + 일하는 시간 안 빈 칸(기본 길이) | 그 칸에 넣기 |
| commit_match | 오늘 커밋 메시지와 제목이 겹치는 끝내지 않은 할 일 | 끝냄으로 |

`unscheduled_long`(빈 칸보다 긴 일 나눠 넣기)은 2차 범위.

학습(`BehaviorModel`)을 넘기면 빈 칸은 "평소 하던 시간"부터, 길이는 태그별로 실제 걸린
만큼 찾고, 여러 번 미룬 지난 마감 일에는 "내려놓기"(휴지통)를 맨 앞에 둔다. 넘기지 않으면
지금까지와 같다. 순서·노출은 `suggestion_ranker.rank` 가 따로 정한다.
"""

import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from app.ai.domain.models.learning import BehaviorModel
from app.ai.domain.models.snapshots import TodoSnapshot
from app.ai.domain.models.suggestion import SuggestionAction, SuggestionCandidate
from app.ai.domain.services.suggestion_ranker import (
    estimate_minutes,
    hour_profile,
    is_usual_hour,
    slot_score,
)

MAX_OVERDUE = 10
MAX_FREE_SLOT = 3
MAX_COMMIT_MATCH = 3
_SLOT_GRANULARITY = timedelta(minutes=15)
DEFER_THRESHOLD = 2  # 이만큼 뒤로 미룬 일은 "내려놓기"를 먼저 권한다
_URGENCY_DAYS = 14

_TEXT: dict[str, dict[str, str]] = {
    "ko": {
        "overdue_reason": "{md} 마감이 지났어요",
        "to_today": "오늘로",
        "to_tomorrow": "내일로",
        "free_reason": "일하는 시간에 빈 칸이 있어요",
        "free_label": "{start}~{end}에 넣기",
        "commit_reason": "커밋 '{message}'과(와) 맞아요",
        "mark_done": "끝냄으로",
        "deferred_reason": "{n}번 미룬 일이에요",
        "drop": "내려놓기",
        "usual_time": "평소 {hour}시쯤 하던 일이에요",
        "usual_length": "보통 {minutes}분 걸렸어요",
    },
    "en": {
        "overdue_reason": "Past due since {md}",
        "to_today": "Move to today",
        "to_tomorrow": "Move to tomorrow",
        "free_reason": "There is a free slot in your work hours",
        "free_label": "Schedule {start}–{end}",
        "commit_reason": "Matches commit '{message}'",
        "mark_done": "Mark done",
        "deferred_reason": "Put off {n} times",
        "drop": "Let it go",
        "usual_time": "You usually do this around {hour}:00",
        "usual_length": "Usually takes {minutes} min",
    },
}


def texts(locale: str | None) -> dict[str, str]:
    base = (locale or "ko").split("-")[0].split("_")[0].lower()
    return _TEXT.get(base, _TEXT["en"])


def _md(date_key: str) -> str:
    d = date.fromisoformat(date_key)
    return f"{d.month}/{d.day}"


# ── 지난 마감 ──────────────────────────────────────────────────────────────


def overdue_suggestions(
    overdue: list[TodoSnapshot],
    today: date,
    t: dict[str, str],
    deferrals: dict[str, int] | None = None,
) -> list[SuggestionCandidate]:
    """`deferrals`(할 일 id → 최근 뒤로 미룬 횟수)가 DEFER_THRESHOLD 이상이면 이유를 바꾸고
    "내려놓기"(휴지통, 되돌리면 되살림)를 맨 앞에 둔다. 반복 회차는 휴지통으로 못 보내 뺀다."""
    tomorrow = today + timedelta(days=1)
    out: list[SuggestionCandidate] = []
    for todo in overdue[:MAX_OVERDUE]:
        due = todo.due_date_key or todo.date_key
        late_days = (today - date.fromisoformat(due)).days
        deferred = (deferrals or {}).get(todo.id, 0)

        def move(to: date, todo: TodoSnapshot = todo) -> dict[str, str]:
            # 마감이 따로 있으면 함께 옮긴다 — due_date_key >= date_key 제약에 걸리지 않게.
            patch = {"date_key": to.isoformat()}
            if todo.due_date_key is not None:
                patch["due_date_key"] = to.isoformat()
            return patch

        actions: tuple[SuggestionAction, ...] = (
            SuggestionAction(t["to_today"], move(today), "to_today"),
            SuggestionAction(t["to_tomorrow"], move(tomorrow), "to_tomorrow"),
        )
        reason, reason_code = t["overdue_reason"].format(md=_md(due)), "overdue"
        if deferred >= DEFER_THRESHOLD:
            reason, reason_code = t["deferred_reason"].format(n=deferred), "overdue_deferred"
            if not todo.recurring:
                actions = (SuggestionAction(t["drop"], {}, "drop"), *actions)
        out.append(
            SuggestionCandidate(
                kind="overdue",
                todo_id=todo.id,
                title=todo.title,
                reason=reason,
                actions=actions,
                reason_code=reason_code,
                urgency=1.0 + min(max(late_days, 0), _URGENCY_DAYS) / _URGENCY_DAYS,
                learned=reason_code == "overdue_deferred",
                tag=todo.tag,
            )
        )
    return out


# ── 빈 칸 ─────────────────────────────────────────────────────────────────


def _ceil(dt: datetime, step: timedelta) -> datetime:
    epoch = datetime(2000, 1, 1, tzinfo=dt.tzinfo)
    remainder = (dt - epoch) % step
    return dt if not remainder else dt + (step - remainder)


def find_free_slots(
    work_start: datetime,
    work_end: datetime,
    busy: list[tuple[datetime, datetime]],
    length: timedelta,
    count: int,
    not_before: datetime | None = None,
) -> list[tuple[datetime, datetime]]:
    """일하는 시간 안에서 busy 와 겹치지 않는 길이 `length` 의 칸을 앞에서부터 count 개.

    찾은 칸은 다음 칸 계산에서 busy 로 친다(같은 칸에 두 일이 들어가지 않게).
    """
    cursor = _ceil(max(work_start, not_before or work_start), _SLOT_GRANULARITY)
    taken = sorted(busy)
    slots: list[tuple[datetime, datetime]] = []
    while len(slots) < count and cursor + length <= work_end:
        end = cursor + length
        clash = next((b for b in taken if b[0] < end and cursor < b[1]), None)
        if clash is not None:
            cursor = _ceil(clash[1], _SLOT_GRANULARITY)
            continue
        slots.append((cursor, end))
        taken = sorted([*taken, (cursor, end)])
        cursor = end
    return slots


def best_free_slot(
    work_start: datetime,
    work_end: datetime,
    busy: list[tuple[datetime, datetime]],
    length: timedelta,
    not_before: datetime | None = None,
    score: Callable[[datetime, datetime], float] | None = None,
) -> tuple[datetime, datetime] | None:
    """busy 와 겹치지 않는 길이 `length` 칸 중 score 가 가장 큰 것(같으면 이른 것).

    score 가 없으면 가장 이른 칸 — `find_free_slots` 의 한 칸과 같다.
    """
    cursor = _ceil(max(work_start, not_before or work_start), _SLOT_GRANULARITY)
    best: tuple[datetime, datetime] | None = None
    best_score = float("-inf")
    while cursor + length <= work_end:
        end = cursor + length
        if not any(b[0] < end and cursor < b[1] for b in busy):
            if score is None:
                return cursor, end
            value = score(cursor, end)
            if value > best_score:
                best, best_score = (cursor, end), value
        cursor += _SLOT_GRANULARITY
    return best


def free_slot_suggestions(
    todos: list[TodoSnapshot],
    work_start: datetime,
    work_end: datetime,
    default_minutes: int,
    tz_name: str,
    t: dict[str, str],
    now: datetime | None = None,
    model: BehaviorModel | None = None,
) -> list[SuggestionCandidate]:
    """그날의 시간 없는 할 일을 일하는 시간 안 빈 칸에 넣자고 한다. 시간 있는 할 일이 busy.

    할 일마다 차례로 한 칸씩 — 찾은 칸은 다음 할 일의 busy 가 된다. `model` 이 있으면 길이는
    태그별 추정, 칸은 평소 하던 시간대 쪽(증거가 충분할 때만).
    """
    tz = work_start.tzinfo
    # 칸 계산은 UTC 로 — 같은 ZoneInfo 끼리의 덧셈은 벽시계 기준이라
    # 서머타임 전환일에 길이가 틀어진다.
    busy: list[tuple[datetime, datetime]] = [
        (x.start_time, x.end_time)  # type: ignore[misc]
        for x in todos
        if x.is_timed
    ]
    candidates = [x for x in todos if x.is_open and x.start_time is None]
    out: list[SuggestionCandidate] = []
    for todo in candidates:
        if len(out) >= MAX_FREE_SLOT:
            break
        minutes, length_learned = (
            estimate_minutes(model, todo.tag, default_minutes)
            if model is not None
            else (default_minutes, False)
        )
        profile = hour_profile(model, todo.tag) if model is not None else None
        score: Callable[[datetime, datetime], float] | None = None
        if profile is not None:
            probs = profile[0]

            def _score(a: datetime, b: datetime, probs: list[float] = probs) -> float:
                return slot_score(probs, a.astimezone(tz), b.astimezone(tz))

            score = _score

        found = best_free_slot(
            work_start.astimezone(UTC),
            work_end.astimezone(UTC),
            busy,
            timedelta(minutes=minutes),
            not_before=now.astimezone(UTC) if now else None,
            score=score,
        )
        if found is None:
            continue
        start, end = found
        busy.append(found)
        local_start, local_end = start.astimezone(tz), end.astimezone(tz)

        reason, reason_code = t["free_reason"], "free_slot"
        if profile is not None and is_usual_hour(profile[0], local_start.hour):
            reason = t["usual_time"].format(hour=local_start.hour)
            reason_code = "free_slot_usual_time"
        if length_learned:
            length_text = t["usual_length"].format(minutes=minutes)
            if reason_code == "free_slot":
                reason, reason_code = length_text, "free_slot_usual_length"
            else:
                reason = f"{reason} · {length_text}"
        out.append(
            SuggestionCandidate(
                kind="free_slot",
                todo_id=todo.id,
                title=todo.title,
                reason=reason,
                slot=(start, end),
                actions=(
                    SuggestionAction(
                        t["free_label"].format(
                            start=local_start.strftime("%H:%M"), end=local_end.strftime("%H:%M")
                        ),
                        {
                            "start_time": start.isoformat(),
                            "end_time": end.isoformat(),
                            "timezone": tz_name,
                        },
                        "schedule",
                    ),
                ),
                reason_code=reason_code,
                learned=reason_code != "free_slot",
                tag=todo.tag,
            )
        )
    return out


# ── 커밋과 맞는 할 일 ──────────────────────────────────────────────────────

_WORD = re.compile(r"\w{2,}", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text)}


def commit_match_suggestions(
    todos: list[TodoSnapshot], commit_messages: list[str], t: dict[str, str]
) -> list[SuggestionCandidate]:
    """제목 낱말 두 개 이상이 한 커밋 메시지에 있거나,
    네 글자 이상 제목이 메시지에 통째로 있으면."""
    out: list[SuggestionCandidate] = []
    for todo in todos:
        if not todo.is_open or len(out) >= MAX_COMMIT_MATCH:
            continue
        title_tokens = _tokens(todo.title)
        for message in commit_messages:
            shared = title_tokens & _tokens(message)
            whole = len(todo.title.strip()) >= 4 and todo.title.strip().lower() in message.lower()
            if len(shared) >= 2 or whole:
                out.append(
                    SuggestionCandidate(
                        kind="commit_match",
                        todo_id=todo.id,
                        title=todo.title,
                        reason=t["commit_reason"].format(message=message[:40]),
                        actions=(
                            SuggestionAction(t["mark_done"], {"status": "done"}, "mark_done"),
                        ),
                        reason_code="commit_match",
                        tag=todo.tag,
                    )
                )
                break
    return out
