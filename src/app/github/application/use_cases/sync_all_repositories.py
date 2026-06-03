from datetime import datetime, timezone

from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.github.application.dtos.commands import SyncAllRepositoriesCommand
from app.github.application.use_cases._token import get_github_access_token
from app.github.domain.models.github_repository import GitHubRepository
from app.github.domain.repositories.repository import IGitHubRepositoryRepository
from app.github.infrastructure.api.github_api_client import GitHubApiClient
from app.shared.domain.utils.id import generate_id


class SyncAllRepositoriesUseCase:
    """One-shot full sync of the user's GitHub repos at this point in time.

    Existing links are kept (idempotent upsert). Repos deleted on GitHub after
    a previous sync are NOT removed here — call unlink endpoints for cleanup.
    """

    def __init__(
        self,
        repo: IGitHubRepositoryRepository,
        oauth_repo: IOAuthConnectionRepository,
        api_client: GitHubApiClient,
    ) -> None:
        self._repo = repo
        self._oauth_repo = oauth_repo
        self._api_client = api_client

    async def execute(self, cmd: SyncAllRepositoriesCommand) -> list[GitHubRepository]:
        token = await get_github_access_token(self._oauth_repo, cmd.user_id)
        remote_repos = await self._api_client.list_user_repositories(token)

        existing = {r.github_repo_id: r for r in await self._repo.find_by_user(cmd.user_id)}
        now = datetime.now(timezone.utc)

        to_save: list[GitHubRepository] = []
        for data in remote_repos:
            prior = existing.get(data.github_repo_id)
            to_save.append(GitHubRepository(
                id=prior.id if prior else generate_id("ghrepo"),
                user_id=cmd.user_id,
                github_repo_id=data.github_repo_id,
                owner=data.owner,
                name=data.name,
                full_name=data.full_name,
                is_private=data.is_private,
                default_branch=data.default_branch,
                html_url=data.html_url,
                created_at=prior.created_at if prior else now,
                updated_at=now if prior else None,
            ))

        if not to_save:
            return []
        return await self._repo.save_many(to_save)
