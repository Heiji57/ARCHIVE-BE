from datetime import datetime, timezone

from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.github.application.dtos.commands import LinkRepositoryCommand
from app.github.application.use_cases._token import get_github_access_token
from app.github.domain.exceptions.exceptions import GitHubRepositoryAlreadyLinkedException
from app.github.domain.models.github_repository import GitHubRepository
from app.github.domain.repositories.repository import IGitHubRepositoryRepository
from app.github.infrastructure.api.github_api_client import GitHubApiClient
from app.shared.domain.utils.id import generate_id


class LinkRepositoryUseCase:
    def __init__(
        self,
        repo: IGitHubRepositoryRepository,
        oauth_repo: IOAuthConnectionRepository,
        api_client: GitHubApiClient,
    ) -> None:
        self._repo = repo
        self._oauth_repo = oauth_repo
        self._api_client = api_client

    async def execute(self, cmd: LinkRepositoryCommand) -> GitHubRepository:
        existing = await self._repo.find_by_github_id(cmd.user_id, cmd.github_repo_id)
        if existing:
            raise GitHubRepositoryAlreadyLinkedException()

        token = await get_github_access_token(self._oauth_repo, cmd.user_id)
        data = await self._api_client.get_repository(token, cmd.github_repo_id)

        entity = GitHubRepository(
            id=generate_id("ghrepo"),
            user_id=cmd.user_id,
            github_repo_id=data.github_repo_id,
            owner=data.owner,
            name=data.name,
            full_name=data.full_name,
            is_private=data.is_private,
            default_branch=data.default_branch,
            html_url=data.html_url,
            created_at=datetime.now(timezone.utc),
        )
        return await self._repo.save(entity)
