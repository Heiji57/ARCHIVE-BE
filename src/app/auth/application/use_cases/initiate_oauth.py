"""일반 로그인용 OAuth authorize URL 발급.

Link(계정 연결) 흐름은 별도 InitiateOAuthLinkUseCase 를 사용한다.
"""
from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.infrastructure.cache.oauth_state import OAuthStateCache
from app.auth.infrastructure.oauth.registry import OAuthClientRegistry


class InitiateOAuthUseCase:
    def __init__(self, registry: OAuthClientRegistry, state_cache: OAuthStateCache) -> None:
        self._registry = registry
        self._state_cache = state_cache

    async def execute(self, provider: OAuthProvider) -> str:
        state = await self._state_cache.create_state(provider.value)
        return self._registry.get(provider).get_authorization_url(state)
