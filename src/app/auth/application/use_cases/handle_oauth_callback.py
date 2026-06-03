import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from app.auth.domain.exceptions.exceptions import OAuthStateInvalidException
from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.auth.infrastructure.cache.auth_token import AuthTokenCache
from app.auth.infrastructure.cache.oauth_state import OAuthStateCache
from app.auth.infrastructure.cache.onboarding import OnboardingTokenCache
from app.auth.infrastructure.oauth.registry import OAuthClientRegistry
from app.shared.infrastructure.auth.jwt import create_access_token
from app.user.domain.repositories.repository import IUserRepository


@dataclass(frozen=True)
class OAuthCallbackResult:
    is_onboarding: bool
    # 기존 사용자(is_onboarding=False)인 경우
    access_token: str | None = None
    refresh_token: str | None = None
    # 신규 사용자(is_onboarding=True)인 경우
    onboarding_token: str | None = None


class HandleOAuthCallbackUseCase:
    def __init__(
        self,
        registry: OAuthClientRegistry,
        state_cache: OAuthStateCache,
        oauth_connection_repo: IOAuthConnectionRepository,
        user_repo: IUserRepository,
        auth_token_cache: AuthTokenCache,
        onboarding_cache: OnboardingTokenCache,
    ) -> None:
        self._registry = registry
        self._state_cache = state_cache
        self._oauth_connection_repo = oauth_connection_repo
        self._user_repo = user_repo
        self._auth_token_cache = auth_token_cache
        self._onboarding_cache = onboarding_cache

    async def execute(
        self,
        provider: OAuthProvider,
        code: str,
        state: str,
        device_info: str | None,
    ) -> OAuthCallbackResult:
        stored_provider = await self._state_cache.consume_state(state)
        if stored_provider != provider:
            raise OAuthStateInvalidException()

        client = self._registry.get(provider)
        provider_token = await client.exchange_code(code)
        user_info = await client.get_user_info(provider_token)

        now = datetime.now(timezone.utc)
        existing_connection = await self._oauth_connection_repo.find_by_provider(
            provider, user_info.provider_user_id
        )

        # 기존 OAuth 연결 → 로그인 처리
        if existing_connection:
            existing_connection.access_token = provider_token
            existing_connection.updated_at = now
            await self._oauth_connection_repo.save(existing_connection)
            user = await self._user_repo.find_by_id(existing_connection.user_id)
            assert user is not None
            return await self._issue_session(user.id, device_info)

        # 같은 이메일 기존 사용자 → OAuth 연결 추가 후 로그인 처리
        user = await self._user_repo.find_by_email(user_info.email)
        if user is not None:
            from app.auth.domain.models.oauth_connection import OAuthConnection
            from app.shared.domain.utils.id import generate_id
            connection = OAuthConnection(
                id=generate_id("oauth"),
                user_id=user.id,
                provider=provider,
                provider_user_id=user_info.provider_user_id,
                access_token=provider_token,
                created_at=now,
            )
            await self._oauth_connection_repo.save(connection)
            return await self._issue_session(user.id, device_info)

        # 신규 사용자 → 온보딩 토큰 발급
        onboarding_token = await self._onboarding_cache.create(
            provider=provider.value,
            provider_user_id=user_info.provider_user_id,
            email=user_info.email,
        )
        return OAuthCallbackResult(
            is_onboarding=True,
            onboarding_token=onboarding_token,
        )

    async def _issue_session(self, user_id: str, device_info: str | None) -> OAuthCallbackResult:
        access_token = create_access_token(user_id)
        raw_refresh = secrets.token_urlsafe(32)
        refresh_hash = hashlib.sha256(raw_refresh.encode()).hexdigest()
        await self._auth_token_cache.store(refresh_hash, user_id, device_info)
        return OAuthCallbackResult(
            is_onboarding=False,
            access_token=access_token,
            refresh_token=raw_refresh,
        )
