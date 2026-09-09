from dataclasses import dataclass, field

from app.topic.application.dtos.queries import GetTopicSourcesQuery
from app.topic.application.services.topic_matcher import TopicMatcher
from app.topic.domain.exceptions.exceptions import TopicNotFoundException
from app.topic.domain.repositories.repository import ITopicDigestRepository, ITopicRepository


@dataclass(frozen=True)
class TopicSource:
    kind: str  # "entry" | "todo"
    id: str
    title: str
    date_key: str
    retro_type: str | None = None  # todo 는 항상 None


@dataclass(frozen=True)
class TopicSourcePage:
    items: list[TopicSource] = field(default_factory=list)
    total: int = 0
    page: int = 1
    size: int = 20
    # 이 목록은 "지금" 이 주제에 묶이는 소스를 다시 계산한 결과다. 마지막 정리 문서가 실제로
    # 읽은 범위는 이 워터마크까지이므로, 이후 추가된 회고는 문서에 아직 반영돼 있지 않다.
    digest_watermark_date_key: str | None = None


class GetTopicSourcesUseCase:
    def __init__(
        self,
        topic_repo: ITopicRepository,
        digest_repo: ITopicDigestRepository,
        matcher: TopicMatcher,
    ) -> None:
        self._topic_repo = topic_repo
        self._digest_repo = digest_repo
        self._matcher = matcher

    async def execute(self, query: GetTopicSourcesQuery) -> TopicSourcePage:
        topic = await self._topic_repo.find_by_id(query.topic_id, query.user_id)
        if topic is None:
            raise TopicNotFoundException()

        match = await self._matcher.match(query.user_id, topic)
        digest = await self._digest_repo.find_by_topic(query.topic_id, query.user_id)

        items = [
            TopicSource(
                kind="entry",
                id=e.id,
                title=e.title,
                date_key=e.date_key,
                retro_type=e.retro_type,
            )
            for e in match.entries
        ] + [
            TopicSource(kind="todo", id=t.id, title=t.title, date_key=t.date_key)
            for t in match.todos
        ]
        # date_key 동률 시 id 로 tie-break — 페이지 경계에서 항목이 중복/누락되지 않게 한다.
        items.sort(key=lambda s: (s.date_key, s.id), reverse=True)

        offset = (query.page - 1) * query.size
        return TopicSourcePage(
            items=items[offset : offset + query.size],
            total=len(items),
            page=query.page,
            size=query.size,
            digest_watermark_date_key=digest.watermark_date_key if digest else None,
        )
