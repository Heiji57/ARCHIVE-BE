from dataclasses import dataclass


@dataclass(frozen=True)
class GetEntriesQuery:
    user_id: str
    retro_type: str | None = None
    from_date: str | None = None
    to_date: str | None = None


@dataclass(frozen=True)
class GetEntriesPageQuery:
    user_id: str
    retro_type: str
    page: int
    size: int
    q: str | None = None
