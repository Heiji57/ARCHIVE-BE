from dataclasses import dataclass

from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.github.domain.exceptions.exceptions import GitHubConnectionNotFoundException
from app.github.infrastructure.api.github_api_client import GitHubApiClient


@dataclass(frozen=True)
class GitHubCredentials:
    access_token: str
    login: str
    verified_emails: list[str]
    """GitHub 계정의 verified emails. commit author 매칭에 사용.
    빈 list 면 사용자가 GitHub 에 등록한 verified email 이 없는 상태."""


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
    """GitHub access_token + login + verified emails 반환.

    캐시 우선. 비어있으면 lazy backfill:
    - login: `/user` API
    - verified_emails: `/user/emails` API (`user:email` scope 필요)
    """
    connections = await oauth_repo.find_by_user_id(user_id)
    github_conn = next(
        (c for c in connections if c.provider == OAuthProvider.GITHUB),
        None,
    )
    if github_conn is None or not github_conn.access_token:
        raise GitHubConnectionNotFoundException("Connect GitHub account first.")

    dirty = False

    if github_conn.provider_login is None:
        user = await api_client.get_authenticated_user(github_conn.access_token)
        github_conn.provider_login = user.login
        dirty = True

    if github_conn.provider_verified_emails is None:
        emails = await api_client.get_user_verified_emails(github_conn.access_token)
        github_conn.provider_verified_emails = emails
        dirty = True

    if dirty:
        await oauth_repo.save(github_conn)

    return GitHubCredentials(
        access_token=github_conn.access_token,
        login=github_conn.provider_login,
        verified_emails=list(github_conn.provider_verified_emails or []),
    )
