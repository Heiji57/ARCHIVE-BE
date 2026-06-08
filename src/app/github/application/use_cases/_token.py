from dataclasses import dataclass

from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.github.domain.exceptions.exceptions import GitHubConnectionNotFoundException
from app.github.infrastructure.api.github_api_client import GitHubApiClient


@dataclass(frozen=True)
class GitHubCredentials:
    access_token: str
    login: str


async def get_github_access_token(
    oauth_repo: IOAuthConnectionRepository, user_id: str
) -> str:
    """사용자의 GitHub OAuth access_token 반환.

    빈 문자열로 저장된 케이스(OAuth 온보딩 직후, 아직 GitHub 동의 안 한 사용자)도
    "미연결" 로 간주해 동일 예외를 던진다.
    """
    connections = await oauth_repo.find_by_user_id(user_id)
    github_conn = next(
        (c for c in connections if c.provider == OAuthProvider.GITHUB),
        None,
    )
    if github_conn is None or not github_conn.access_token:
        raise GitHubConnectionNotFoundException("Connect GitHub account first.")
    return github_conn.access_token


async def get_github_credentials(
    oauth_repo: IOAuthConnectionRepository,
    api_client: GitHubApiClient,
    user_id: str,
) -> GitHubCredentials:
    """GitHub access_token + login 동시 반환. login 이 캐시돼 있으면 API 호출 생략.

    구 사용자는 provider_login=NULL 상태 → 첫 호출 시 /user API 로 fetch & 저장 (lazy backfill).
    """
    connections = await oauth_repo.find_by_user_id(user_id)
    github_conn = next(
        (c for c in connections if c.provider == OAuthProvider.GITHUB),
        None,
    )
    if github_conn is None or not github_conn.access_token:
        raise GitHubConnectionNotFoundException("Connect GitHub account first.")

    if github_conn.provider_login:
        return GitHubCredentials(
            access_token=github_conn.access_token,
            login=github_conn.provider_login,
        )

    # Lazy backfill
    user = await api_client.get_authenticated_user(github_conn.access_token)
    github_conn.provider_login = user.login
    await oauth_repo.save(github_conn)
    return GitHubCredentials(
        access_token=github_conn.access_token,
        login=user.login,
    )
