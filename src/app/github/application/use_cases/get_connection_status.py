from dataclasses import dataclass

from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.github.infrastructure.api.github_api_client import GitHubApiClient
from app.settings.domain.repositories.repository import IUserSettingsRepository


@dataclass(frozen=True)
class ConnectionStatus:
    connected: bool
    login: str | None
    push_target_repository_id: str | None
    has_verified_emails: bool
    """GitHub `/user/emails` 캐시에 verified emails 가 1개 이상 있는지.
    False 면 commit author 매칭이 login 으로만 동작 — 사용자가 gitbash 등
    로컬 git config 로 push 한 commit 이 표시 안 될 가능성 → 재연결 유도용 신호.
    """


class GetConnectionStatusUseCase:
    """GitHub OAuth 연결 상태 + push target + verified emails 보유 여부 통합 조회.

    FE가 GitHub 화면 진입 시 한 번에 상태 파악할 수 있도록 묶어 반환.
    """

    def __init__(
        self,
        oauth_repo: IOAuthConnectionRepository,
        settings_repo: IUserSettingsRepository,
        api_client: GitHubApiClient,
    ) -> None:
        self._oauth_repo = oauth_repo
        self._settings_repo = settings_repo
        self._api_client = api_client

    async def execute(self, user_id: str) -> ConnectionStatus:
        settings = await self._settings_repo.find_by_user_id(user_id)
        push_target_id = settings.github_push_target_repository_id if settings else None

        connections = await self._oauth_repo.find_by_user_id(user_id)
        github_conn = next(
            (c for c in connections if c.provider == OAuthProvider.GITHUB),
            None,
        )
        if github_conn is None or not github_conn.access_token:
            return ConnectionStatus(
                connected=False,
                login=None,
                push_target_repository_id=push_target_id,
                has_verified_emails=False,
            )

        emails = github_conn.provider_verified_emails or []
        has_verified_emails = len(emails) > 0

        # 토큰 유효성 확인을 위해 login 조회 — 실패해도 throw하지 않고 connected=False
        try:
            authenticated = await self._api_client.get_authenticated_user(
                github_conn.access_token
            )
            return ConnectionStatus(
                connected=True,
                login=authenticated.login,
                push_target_repository_id=push_target_id,
                has_verified_emails=has_verified_emails,
            )
        except Exception:
            return ConnectionStatus(
                connected=False,
                login=None,
                push_target_repository_id=push_target_id,
                has_verified_emails=has_verified_emails,
            )
