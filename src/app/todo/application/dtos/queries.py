from dataclasses import dataclass


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
    tz: str     # IANA timezone


@dataclass(frozen=True)
class SearchTagsQuery:
    user_id: str
    query: str
    limit: int
