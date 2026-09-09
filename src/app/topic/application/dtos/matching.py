from dataclasses import dataclass, field


@dataclass(frozen=True)
class MatchedEntry:
    id: str
    title: str
    date_key: str
    retro_type: str


@dataclass(frozen=True)
class MatchedTodo:
    id: str
    title: str
    date_key: str
    status: str
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TopicMatch:
    """한 토픽에 묶이는 회고/할일 — digest 생성과 동일한 벡터 매칭 규칙의 결과."""

    entries: list[MatchedEntry] = field(default_factory=list)
    todos: list[MatchedTodo] = field(default_factory=list)
