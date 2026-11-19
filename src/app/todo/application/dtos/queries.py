from dataclasses import dataclass

from app.shared.domain.utils.period import WeekStart


@dataclass(frozen=True)
class GetTodosByDateQuery:
    user_id: str
    date_key: str


@dataclass(frozen=True)
class GetTodosByRangeQuery:
    user_id: str
    from_date: str
    to_date: str


@dataclass(frozen=True)
class GetTodoStatsQuery:
    user_id: str
    range: str  # "today" | "week" | "month"
    tz: str  # IANA timezone
    week_start: WeekStart = "mon"  # range=week 와 7일 trend 의 경계


@dataclass(frozen=True)
class SearchTagsQuery:
    user_id: str
    query: str
    limit: int


@dataclass(frozen=True)
class GetTodosFilteredQuery:
    """기간 밖 조회(`GET /todos?overdue|due|calendarPushStatus`). 모드는 하나만 채운다."""

    user_id: str
    tz: str  # overdue 의 "오늘" 기준 — 사용자 IANA tz
    overdue: bool = False
    due_from: str | None = None
    due_to: str | None = None
    push_status: str | None = None
    calendar_ids: list[str] | None = None
    include_default_calendar: bool = False
    page: int = 1
    size: int = 50
    today: str | None = (
        None  # overdue 기준일을 직접 줄 때(호출자가 이미 "오늘"을 정함) — 없으면 tz 의 오늘
    )
