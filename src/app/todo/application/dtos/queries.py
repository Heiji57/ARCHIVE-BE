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
