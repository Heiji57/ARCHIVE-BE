from dataclasses import dataclass


@dataclass(frozen=True)
class GetTopicsQuery:
    user_id: str
    # include=recent — 카드 좌우 넘기기용 "최근에 한 일" 다섯 줄. today 는 사용자 tz 의 오늘.
    include_recent: bool = False
    today: str | None = None


@dataclass(frozen=True)
class GetTopicStatsQuery:
    user_id: str
    topic_id: str


@dataclass(frozen=True)
class GetTopicSourcesQuery:
    user_id: str
    topic_id: str
    page: int = 1
    size: int = 20


@dataclass(frozen=True)
class GetDigestQuery:
    user_id: str
    topic_id: str


@dataclass(frozen=True)
class GetDigestByIdQuery:
    user_id: str
    digest_id: str
