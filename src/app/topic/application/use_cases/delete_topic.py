from app.topic.application.dtos.commands import DeleteTopicCommand
from app.topic.domain.exceptions.exceptions import TopicNotFoundException
from app.topic.domain.repositories.repository import ITopicRepository


class DeleteTopicUseCase:
    def __init__(self, repo: ITopicRepository) -> None:
        self._repo = repo

    async def execute(self, cmd: DeleteTopicCommand) -> None:
        topic = await self._repo.find_by_id(cmd.topic_id, cmd.user_id)
        if topic is None:
            raise TopicNotFoundException()
        await self._repo.delete(cmd.topic_id, cmd.user_id)
