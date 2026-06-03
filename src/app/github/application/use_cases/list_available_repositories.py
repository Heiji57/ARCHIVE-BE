from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.github.application.use_cases._token import get_github_access_token
from app.github.infrastructure.api.github_api_client import GitHubApiClient, GitHubRepoData


class ListAvailableRepositoriesUseCase:
    def __init__(
        self,
        oauth_repo: IOAuthConnectionRepository,
        api_client: GitHubApiClient,
    ) -> None:
        self._oauth_repo = oauth_repo
        self._api_client = api_client

    async def execute(self, user_id: str) -> list[GitHubRepoData]:
        token = await get_github_access_token(self._oauth_repo, user_id)
        return await self._api_client.list_user_repositories(token)
