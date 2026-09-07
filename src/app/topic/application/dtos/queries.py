from dataclasses import dataclass


@dataclass(frozen=True)
class GetTopicsQuery:
    user_id: str


@dataclass(frozen=True)
class GetDigestQuery:
    user_id: str
    topic_id: str


@dataclass(frozen=True)
class GetDigestByIdQuery:
    user_id: str
    digest_id: str
