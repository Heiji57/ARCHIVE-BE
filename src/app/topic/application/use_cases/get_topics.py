from dataclasses import dataclass

import structlog

from app.topic.application.dtos.queries import GetTopicsQuery
from app.topic.application.services.topic_matcher import TopicMatcher
from app.topic.domain.models.topic import Topic
from app.topic.domain.repositories.repository import ITopicDigestRepository, ITopicRepository


_log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class TopicSummary:
    """목록 카드/pill 이 쓰는 토픽 + 집계. 카운트는 stats 엔드포인트와 같은 매칭·캐시를 공유한다.

    카운트는 None 일 수 있다 — 매칭이 임베딩 API 를 타므로 그쪽이 죽으면 카운트만 비운다.
    """

    topic: Topic
    entry_count: int | None
    todo_count: int | None
    digest_watermark_date_key: str | None


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

        # 카운트는 부가 정보다 — 임베딩 API 장애/쿼터 초과로 목록 자체가 죽으면 안 된다.
        try:
            matches = await self._matcher.match_many(query.user_id, topics)
        except Exception:
            _log.warning("get_topics.match_failed", user_id=query.user_id, exc_info=True)
            matches = {}

        summaries = []
        for topic in topics:
            match = matches.get(topic.id)
            digest = await self._digest_repo.find_by_topic(topic.id, query.user_id)
            summaries.append(
                TopicSummary(
                    topic=topic,
                    entry_count=len(match.entries) if match else None,
                    todo_count=len(match.todos) if match else None,
                    digest_watermark_date_key=digest.watermark_date_key if digest else None,
                )
            )
        return summaries
