import hashlib
import secrets
from datetime import datetime, timezone

from app.auth.domain.exceptions.exceptions import OAuthStateInvalidException
from app.auth.domain.models.oauth_connection import OAuthConnection
from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.auth.infrastructure.cache.auth_token import AuthTokenCache
from app.auth.infrastructure.cache.oauth_state import OAuthStateCache
from app.auth.infrastructure.oauth.registry import OAuthClientRegistry
from app.shared.domain.utils.id import generate_id
from app.shared.infrastructure.auth.jwt import create_access_token
from app.user.domain.models.user import User
from app.user.domain.models.value_objects import Email
from app.user.domain.repositories.repository import IUserRepository


class HandleOAuthCallbackUseCase:
    def __init__(
        self,
        registry: OAuthClientRegistry,
        state_cache: OAuthStateCache,
        oauth_connection_repo: IOAuthConnectionRepository,
        user_repo: IUserRepository,
        auth_token_cache: AuthTokenCache,
    ) -> None:
        self._registry = registry
        self._state_cache = state_cache
        self._oauth_connection_repo = oauth_connection_repo
        self._user_repo = user_repo
        self._auth_token_cache = auth_token_cache

    async def execute(
        self,
        provider: OAuthProvider,
        code: str,
        state: str,
        device_info: str | None,
    ) -> dict[str, str]:
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

        if existing_connection:
            existing_connection.access_token = provider_token
            existing_connection.updated_at = now
            await self._oauth_connection_repo.save(existing_connection)
            user = await self._user_repo.find_by_id(existing_connection.user_id)
        else:
            user = await self._user_repo.find_by_email(user_info.email)
            if not user:
                user = User(
                    id=generate_id("user"),
                    email=Email(user_info.email),
                    password_hash=None,
                    created_at=now,
                )
                user = await self._user_repo.save(user)

            connection = OAuthConnection(
                id=generate_id("oauth"),
                user_id=user.id,
                provider=provider,
                provider_user_id=user_info.provider_user_id,
                access_token=provider_token,
                created_at=now,
            )
            await self._oauth_connection_repo.save(connection)

        access_token = create_access_token(user.id)
        raw_refresh = secrets.token_urlsafe(32)
        refresh_hash = hashlib.sha256(raw_refresh.encode()).hexdigest()
        await self._auth_token_cache.store(refresh_hash, user.id, device_info)

        return {"access_token": access_token, "refresh_token": raw_refresh}
