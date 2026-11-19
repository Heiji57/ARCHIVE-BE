from dataclasses import dataclass

import structlog
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.shared.domain.exceptions.external import AIServiceException
from app.topic.application.dtos.queries import GetTopicsQuery
from app.topic.application.services.topic_matcher import TopicMatcher
from app.topic.domain.models.structured_digest import DigestItem
from app.topic.domain.models.topic import Topic, TopicDigest
from app.topic.domain.repositories.repository import ITopicDigestRepository, ITopicRepository

_log = structlog.get_logger(__name__)

_RECENT_ITEMS_LIMIT = 5


@dataclass(frozen=True)
class RecentItem:
    date_key: str
    text: str
    theme_key: str


@dataclass(frozen=True)
class TopicSummary:
    """목록 카드가 쓰는 토픽 + 집계. 카운트는 stats 엔드포인트와 같은 매칭·캐시를 공유한다.

    매칭 기반 값(카운트·미반영 수)은 None 일 수 있다 — 매칭이 임베딩 API 를 타므로 그쪽이
    죽으면 그 값만 비운다.
    """

    topic: Topic
    entry_count: int | None
    todo_count: int | None
    digest_watermark_date_key: str | None
    digest_status: str = "none"  # none | pending | in_progress | completed | failed
    digest_summary: str | None = None
    period_start_date_key: str | None = None
    period_end_date_key: str | None = None
    unreflected_entry_count: int | None = None
    recent_items: list[RecentItem] | None = None  # include=recent 일 때만


class GetTopicsUseCase:
    def __init__(
        self,
        repo: ITopicRepository,
        digest_repo: ITopicDigestRepository,
        matcher: TopicMatcher,
    ) -> None:
        self._repo = repo
        self._digest_repo = digest_repo
        self._matcher = matcher

    async def execute(self, query: GetTopicsQuery) -> list[TopicSummary]:
        topics = await self._repo.find_all_by_user(query.user_id)
        if not topics:
            return []

        # 카운트는 부가 정보다 — 임베딩 API 장애/쿼터 초과, 매칭 캐시·락(Redis) 장애, 벡터
        # 검색 DB 오류(매처가 SAVEPOINT 로 격리)로 목록 자체가 죽으면 안 된다.
        # 그 외(코드 버그)는 degrade 로 가리지 않고 전파한다.
        try:
            matches = await self._matcher.match_many(query.user_id, topics)
        except (AIServiceException, RedisError, SQLAlchemyError):
            _log.warning("get_topics.match_failed", user_id=query.user_id, exc_info=True)
            matches = {}

        # digest 배치 조회 — topic 수만큼 왕복하던 N+1 을 한 번으로 접는다.
        digests = await self._digest_repo.find_by_topics([t.id for t in topics], query.user_id)

        summaries = []
        for topic in topics:
            match = matches.get(topic.id)
            digest = digests.get(topic.id)
            watermark = digest.watermark_date_key if digest else None
            period = _period(digest, match)
            summaries.append(
                TopicSummary(
                    topic=topic,
                    entry_count=len(match.entries) if match else None,
                    todo_count=len(match.todos) if match else None,
                    digest_watermark_date_key=watermark,
                    digest_status=digest.status.value if digest else "none",
                    digest_summary=(
                        digest.structured.summary if digest and digest.structured else None
                    ),
                    period_start_date_key=period[0] if period else None,
                    period_end_date_key=period[1] if period else None,
                    # stats 와 같은 계산 — 워터마크 "초과" 날짜의 회고 수.
                    unreflected_entry_count=(
                        sum(1 for e in match.entries if watermark is None or e.date_key > watermark)
                        if match
                        else None
                    ),
                    recent_items=(_recent(digest, query.today) if query.include_recent else None),
                )
            )
        return summaries


def _period(digest: TopicDigest | None, match) -> tuple[str, str] | None:  # type: ignore[no-untyped-def]
    """근거의 처음~마지막 날짜 — 정리가 있으면 정리 항목 기준, 없으면 매칭 결과 기준."""
    if digest is not None and digest.structured is not None:
        period = digest.structured.period()
        if period is not None:
            return period
    if match is None:
        return None
    dates = [e.date_key for e in match.entries] + [t.date_key for t in match.todos]
    return (min(dates), max(dates)) if dates else None


def _recent(digest: TopicDigest | None, today: str | None) -> list[RecentItem]:
    if digest is None or digest.structured is None or today is None:
        return []
    pairs: list[tuple[DigestItem, str]] = digest.structured.recent_items(today, _RECENT_ITEMS_LIMIT)
    return [RecentItem(date_key=i.date_key, text=i.text, theme_key=k) for i, k in pairs]
