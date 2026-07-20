from app.github.application.dtos.commands import UnlinkRepositoryCommand
from app.github.domain.exceptions.exceptions import GitHubRepositoryNotFoundException
from app.github.domain.repositories.repository import IGitHubRepositoryRepository


class UnlinkRepositoryUseCase:
    def __init__(self, repo: IGitHubRepositoryRepository) -> None:
        self._repo = repo

    async def execute(self, cmd: UnlinkRepositoryCommand) -> None:
        existing = await self._repo.find_by_id(cmd.repository_id, cmd.user_id)
        if not existing:
            raise GitHubRepositoryNotFoundException()
        await self._repo.delete(cmd.repository_id, cmd.user_id)
