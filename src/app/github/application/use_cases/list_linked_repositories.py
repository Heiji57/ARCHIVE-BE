from app.github.domain.models.github_repository import GitHubRepository
from app.github.domain.repositories.repository import IGitHubRepositoryRepository


class ListLinkedRepositoriesUseCase:
    def __init__(self, repo: IGitHubRepositoryRepository) -> None:
        self._repo = repo

    async def execute(self, user_id: str) -> list[GitHubRepository]:
        return await self._repo.find_by_user(user_id)
