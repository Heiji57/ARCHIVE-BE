from datetime import datetime, timezone

from app.shared.domain.utils.id import generate_id
from app.shared.infrastructure.config.topic import TopicConfig
from app.topic.application.dtos.commands import CreateTopicCommand
from app.topic.domain.exceptions.exceptions import (
    TopicLimitReachedException,
    TopicNameDuplicatedException,
)
from app.topic.domain.models.topic import Topic
from app.topic.domain.repositories.repository import ITopicRepository


class CreateTopicUseCase:
    def __init__(self, repo: ITopicRepository, config: TopicConfig) -> None:
        self._repo = repo
        self._config = config

    async def execute(self, cmd: CreateTopicCommand) -> Topic:
        if await self._repo.exists_by_name(cmd.user_id, cmd.name):
            raise TopicNameDuplicatedException()

        count = await self._repo.count_by_user(cmd.user_id)
        if count >= self._config.topic_max_per_user:
            raise TopicLimitReachedException(self._config.topic_max_per_user)

        now = datetime.now(timezone.utc)
        topic = Topic(
            id=generate_id("topic"),
            user_id=cmd.user_id,
            name=cmd.name,
            description=cmd.description,
            created_at=now,
        )
        return await self._repo.save(topic)
