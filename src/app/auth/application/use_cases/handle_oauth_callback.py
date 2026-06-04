from dataclasses import dataclass
from datetime import datetime, timezone

from app.auth.application.services.session_service import RequestMeta, SessionService
from app.auth.domain.exceptions.exceptions import (
    OAuthAccountAlreadyLinkedException,
    OAuthProviderAlreadyLinkedException,
    OAuthStateInvalidException,
)
from app.auth.domain.models.oauth_connection import OAuthConnection
from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.auth.infrastructure.cache.oauth_state import OAuthStateCache
from app.auth.infrastructure.cache.onboarding import OnboardingTokenCache
from app.auth.infrastructure.oauth.registry import OAuthClientRegistry
from app.shared.domain.utils.id import generate_id
from app.shared.infrastructure.auth.jwt import create_access_token
from app.user.domain.repositories.repository import IUserRepository


@dataclass(frozen=True)
class OAuthCallbackResult:
    # 결과 종류: login | onboarding | linked
    kind: str
    # 기존 사용자 로그인(kind="login") 또는 link 후 자동 로그인(kind="linked")
    access_token: str | None = None
    refresh_token: str | None = None
    # 신규 사용자 온보딩(kind="onboarding")
    onboarding_token: str | None = None
    # link 결과
    linked_provider: str | None = None


class HandleOAuthCallbackUseCase:
    def __init__(
        self,
        registry: OAuthClientRegistry,
        state_cache: OAuthStateCache,
        oauth_connection_repo: IOAuthConnectionRepository,
        user_repo: IUserRepository,
        session_service: SessionService,
        onboarding_cache: OnboardingTokenCache,
    ) -> None:
        self._registry = registry
        self._state_cache = state_cache
        self._oauth_connection_repo = oauth_connection_repo
        self._user_repo = user_repo
        self._session_service = session_service
        self._onboarding_cache = onboarding_cache

    async def execute(
        self,
        provider: OAuthProvider,
        code: str,
        state: str,
        device_info: str | None,
        ip: str | None = None,
    ) -> OAuthCallbackResult:
        state_payload = await self._state_cache.consume_state(state)
        if state_payload.get("provider") != provider.value:
            raise OAuthStateInvalidException()

        client = self._registry.get(provider)
        provider_token = await client.exchange_code(code)
        user_info = await client.get_user_info(provider_token)

        now = datetime.now(timezone.utc)
        link_user_id = state_payload.get("link_user_id")

        # ── Link 흐름 ─────────────────────────────────────────────────────
        if link_user_id:
            return await self._handle_link(
                provider, user_info, provider_token, link_user_id, now
            )

        # ── 일반 로그인 흐름 ──────────────────────────────────────────────
        existing_connection = await self._oauth_connection_repo.find_by_provider(
            provider, user_info.provider_user_id
        )

        if existing_connection:
            existing_connection.access_token = provider_token
            existing_connection.updated_at = now
            await self._oauth_connection_repo.save(existing_connection)
            user = await self._user_repo.find_by_id(existing_connection.user_id)
            assert user is not None
            return await self._issue_session(user.id, device_info, ip)

        # 같은 이메일 기존 사용자 → OAuth 연결 추가 후 로그인 처리
        user = await self._user_repo.find_by_email(user_info.email)
        if user is not None:
            connection = OAuthConnection(
                id=generate_id("oauth"),
                user_id=user.id,
                provider=provider,
                provider_user_id=user_info.provider_user_id,
                access_token=provider_token,
                created_at=now,
            )
            await self._oauth_connection_repo.save(connection)
            return await self._issue_session(user.id, device_info, ip)

        # 신규 사용자 → 온보딩 토큰
        onboarding_token = await self._onboarding_cache.create(
            provider=provider.value,
            provider_user_id=user_info.provider_user_id,
            email=user_info.email,
        )
        return OAuthCallbackResult(kind="onboarding", onboarding_token=onboarding_token)

    async def _handle_link(
        self,
        provider: OAuthProvider,
        user_info,
        provider_token: str,
        link_user_id: str,
        now: datetime,
    ) -> OAuthCallbackResult:
        # 동일 provider 계정이 다른 사용자에 이미 연결되어 있는지
        existing_connection = await self._oauth_connection_repo.find_by_provider(
            provider, user_info.provider_user_id
        )
        if existing_connection and existing_connection.user_id != link_user_id:
            raise OAuthAccountAlreadyLinkedException(
                "This GitHub account is already linked to another user."
            )

        # 현재 사용자가 같은 provider에 이미 연결되어 있는지 (provider당 1개 정책)
        current_user_connections = await self._oauth_connection_repo.find_by_user_id(
            link_user_id
        )
        same_provider_existing = next(
            (c for c in current_user_connections if c.provider == provider),
            None,
        )
        if same_provider_existing:
            # 동일 provider_user_id면 token만 갱신 (멱등)
            if same_provider_existing.provider_user_id == user_info.provider_user_id:
                same_provider_existing.access_token = provider_token
                same_provider_existing.updated_at = now
                await self._oauth_connection_repo.save(same_provider_existing)
                return OAuthCallbackResult(
                    kind="linked", linked_provider=provider.value
                )
            # 다른 provider account면 reject (한 사용자당 provider 1개)
            raise OAuthProviderAlreadyLinkedException(
                f"You already have a {provider.value} account linked. "
                "Unlink the existing one first."
            )

        # 신규 link
        connection = OAuthConnection(
            id=generate_id("oauth"),
            user_id=link_user_id,
            provider=provider,
            provider_user_id=user_info.provider_user_id,
            access_token=provider_token,
            created_at=now,
        )
        await self._oauth_connection_repo.save(connection)
        return OAuthCallbackResult(kind="linked", linked_provider=provider.value)

    async def _issue_session(
        self, user_id: str, device_info: str | None, ip: str | None
    ) -> OAuthCallbackResult:
        issued = await self._session_service.issue(
            user_id, RequestMeta(user_agent=device_info, ip=ip)
        )
        return OAuthCallbackResult(
            kind="login",
            access_token=create_access_token(user_id),
            refresh_token=issued.refresh_token,
        )
