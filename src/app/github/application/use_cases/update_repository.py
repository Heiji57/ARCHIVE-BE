from dataclasses import dataclass
from datetime import datetime, timezone

from app.github.domain.exceptions.exceptions import GitHubRepositoryNotFoundException
from app.github.domain.models.github_repository import GitHubRepository
from app.github.domain.repositories.repository import IGitHubRepositoryRepository


@dataclass(frozen=True)
class UpdateRepositoryCommand:
    user_id: str
    repository_id: str
    commit_read_enabled: bool


class UpdateRepositoryUseCase:
    def __init__(self, repo: IGitHubRepositoryRepository) -> None:
        self._repo = repo

    async def execute(self, cmd: UpdateRepositoryCommand) -> GitHubRepository:
        entity = await self._repo.find_by_id(cmd.repository_id, cmd.user_id)
        if entity is None:
            raise GitHubRepositoryNotFoundException(cmd.repository_id)
        entity.commit_read_enabled = cmd.commit_read_enabled
        entity.updated_at = datetime.now(timezone.utc)
        return await self._repo.save(entity)
