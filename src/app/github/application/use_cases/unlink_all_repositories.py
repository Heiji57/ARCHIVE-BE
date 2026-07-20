from app.github.domain.repositories.repository import IGitHubRepositoryRepository


class UnlinkAllRepositoriesUseCase:
    def __init__(self, repo: IGitHubRepositoryRepository) -> None:
        self._repo = repo

    async def execute(self, user_id: str) -> None:
        await self._repo.delete_all_by_user(user_id)
