from app.topic.application.dtos.queries import GetTopicsQuery
from app.topic.domain.models.topic import Topic
from app.topic.domain.repositories.repository import ITopicRepository


class GetTopicsUseCase:
    def __init__(self, repo: ITopicRepository) -> None:
        self._repo = repo

    async def execute(self, query: GetTopicsQuery) -> list[Topic]:
        return await self._repo.find_all_by_user(query.user_id)
