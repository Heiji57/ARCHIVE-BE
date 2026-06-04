"""로그인된 사용자의 OAuth provider 계정 link 흐름 시작.

InitiateOAuthUseCase 와 별도 use case 로 분리한 이유:
- 일반 로그인 흐름은 인증 불필요 (GET /authorize)
- link 흐름은 Bearer 필수 (POST /link/init)
- 두 흐름의 라우터 보안 정책이 다르므로 use case 도 분리해 의도를 명확히 한다.
"""
from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.infrastructure.cache.oauth_state import OAuthStateCache
from app.auth.infrastructure.oauth.registry import OAuthClientRegistry


class InitiateOAuthLinkUseCase:
    def __init__(
        self,
        registry: OAuthClientRegistry,
        state_cache: OAuthStateCache,
    ) -> None:
        self._registry = registry
        self._state_cache = state_cache

    async def execute(self, provider: OAuthProvider, user_id: str) -> str:
        state = await self._state_cache.create_link_state(provider.value, user_id)
        return self._registry.get(provider).get_authorization_url(state)
