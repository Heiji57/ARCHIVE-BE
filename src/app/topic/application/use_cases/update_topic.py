from datetime import datetime, timezone

from app.topic.application.dtos.commands import UpdateTopicCommand
from app.topic.domain.exceptions.exceptions import (
    TopicNameDuplicatedException,
    TopicNotFoundException,
)
from app.topic.domain.models.topic import Topic
from app.topic.domain.repositories.repository import ITopicRepository


class UpdateTopicUseCase:
    def __init__(self, repo: ITopicRepository) -> None:
        self._repo = repo

    async def execute(self, cmd: UpdateTopicCommand) -> Topic:
        topic = await self._repo.find_by_id(cmd.topic_id, cmd.user_id)
        if topic is None:
            raise TopicNotFoundException()

        if cmd.name is not None and cmd.name != topic.name:
            # 이름이 실제로 바뀔 때만 검사한다 — 그대로 두는 경우 자기 자신이 걸려 오탐이 난다.
            if await self._repo.exists_by_name(cmd.user_id, cmd.name):
                raise TopicNameDuplicatedException()
            topic.name = cmd.name

        if cmd.description is not None:
            topic.description = cmd.description

        topic.updated_at = datetime.now(timezone.utc)
        return await self._repo.save(topic)
