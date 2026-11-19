"""규칙 기반 추천 — LLM 없이 만든다(비용 0, 결정적). 이유 문장도 템플릿.

| 종류 | 규칙 | 행동 |
|---|---|---|
| overdue | 끝내지 않았고 마감(due, 없으면 date)이 오늘 이전 | 오늘로 / 내일로 |
| free_slot | 오늘의 시간 없는 할 일 + 일하는 시간 안 빈 칸(기본 길이) | 그 칸에 넣기 |
| commit_match | 오늘 커밋 메시지와 제목이 겹치는 끝내지 않은 할 일 | 끝냄으로 |

`unscheduled_long`(빈 칸보다 긴 일 나눠 넣기)은 2차 범위.
"""

import re
from datetime import UTC, date, datetime, timedelta

from app.ai.domain.models.snapshots import TodoSnapshot
from app.ai.domain.models.suggestion import SuggestionAction, SuggestionCandidate

MAX_OVERDUE = 10
MAX_FREE_SLOT = 3
MAX_COMMIT_MATCH = 3
_SLOT_GRANULARITY = timedelta(minutes=15)

_TEXT: dict[str, dict[str, str]] = {
    "ko": {
        "overdue_reason": "{md} 마감이 지났어요",
        "to_today": "오늘로",
        "to_tomorrow": "내일로",
        "free_reason": "일하는 시간에 빈 칸이 있어요",
        "free_label": "{start}~{end}에 넣기",
        "commit_reason": "커밋 '{message}'과(와) 맞아요",
        "mark_done": "끝냄으로",
    },
    "en": {
        "overdue_reason": "Past due since {md}",
        "to_today": "Move to today",
        "to_tomorrow": "Move to tomorrow",
        "free_reason": "There is a free slot in your work hours",
        "free_label": "Schedule {start}–{end}",
        "commit_reason": "Matches commit '{message}'",
        "mark_done": "Mark done",
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
    overdue: list[TodoSnapshot], today: date, t: dict[str, str]
) -> list[SuggestionCandidate]:
    tomorrow = today + timedelta(days=1)
    out: list[SuggestionCandidate] = []
    for todo in overdue[:MAX_OVERDUE]:
        due = todo.due_date_key or todo.date_key

        def move(to: date, todo: TodoSnapshot = todo) -> dict[str, str]:
            # 마감이 따로 있으면 함께 옮긴다 — due_date_key >= date_key 제약에 걸리지 않게.
            patch = {"date_key": to.isoformat()}
            if todo.due_date_key is not None:
                patch["due_date_key"] = to.isoformat()
            return patch

        out.append(
            SuggestionCandidate(
                kind="overdue",
                todo_id=todo.id,
                title=todo.title,
                reason=t["overdue_reason"].format(md=_md(due)),
                actions=(
                    SuggestionAction(t["to_today"], move(today)),
                    SuggestionAction(t["to_tomorrow"], move(tomorrow)),
                ),
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


def free_slot_suggestions(
    todos: list[TodoSnapshot],
    work_start: datetime,
    work_end: datetime,
    default_minutes: int,
    tz_name: str,
    t: dict[str, str],
    now: datetime | None = None,
) -> list[SuggestionCandidate]:
    """그날의 시간 없는 할 일을 일하는 시간 안 빈 칸에 넣자고 한다. 시간 있는 할 일이 busy."""
    busy = [(x.start_time, x.end_time) for x in todos if x.is_timed]
    candidates = [x for x in todos if x.is_open and x.start_time is None]
    # 칸 계산은 UTC 로 — 같은 ZoneInfo 끼리의 덧셈은 벽시계 기준이라
    # 서머타임 전환일에 길이가 틀어진다.
    slots = find_free_slots(
        work_start.astimezone(UTC),
        work_end.astimezone(UTC),
        busy,  # type: ignore[arg-type]
        timedelta(minutes=default_minutes),
        min(len(candidates), MAX_FREE_SLOT),
        not_before=now.astimezone(UTC) if now else None,
    )
    out: list[SuggestionCandidate] = []
    for todo, (start, end) in zip(candidates, slots, strict=False):
        local_start, local_end = (
            start.astimezone(work_start.tzinfo),
            end.astimezone(work_start.tzinfo),
        )
        out.append(
            SuggestionCandidate(
                kind="free_slot",
                todo_id=todo.id,
                title=todo.title,
                reason=t["free_reason"],
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
                    ),
                ),
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
                        actions=(SuggestionAction(t["mark_done"], {"status": "done"}),),
                    )
                )
                break
    return out
