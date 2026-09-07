from app.topic.application.dtos.queries import GetDigestByIdQuery, GetDigestQuery
from app.topic.domain.exceptions.exceptions import DigestNotFoundException, TopicNotFoundException
from app.topic.domain.models.topic import TopicDigest
from app.topic.domain.repositories.repository import ITopicDigestRepository, ITopicRepository


class GetDigestUseCase:
    def __init__(
        self,
        topic_repo: ITopicRepository,
        digest_repo: ITopicDigestRepository,
    ) -> None:
        self._topic_repo = topic_repo
        self._digest_repo = digest_repo

    async def execute(self, query: GetDigestQuery) -> TopicDigest:
        topic = await self._topic_repo.find_by_id(query.topic_id, query.user_id)
        if topic is None:
            raise TopicNotFoundException()

        digest = await self._digest_repo.find_by_topic(query.topic_id, query.user_id)
        if digest is None:
            raise DigestNotFoundException()
        return digest

    async def execute_by_id(self, query: GetDigestByIdQuery) -> TopicDigest:
        digest = await self._digest_repo.find_by_id(query.digest_id, query.user_id)
        if digest is None:
            raise DigestNotFoundException()
        return digest
