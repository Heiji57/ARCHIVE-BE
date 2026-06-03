import hashlib
import secrets
from datetime import datetime, timezone

from app.auth.application.dtos.commands import CompleteOnboardingCommand
from app.auth.domain.exceptions.exceptions import (
    CountryInvalidException,
    CountryRegionRequiredException,
)
from app.auth.domain.models.oauth_connection import OAuthConnection
from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.domain.repositories.repository import IOAuthConnectionRepository
from app.auth.infrastructure.cache.auth_token import AuthTokenCache
from app.auth.infrastructure.cache.onboarding import OnboardingTokenCache
from app.shared.domain.utils.id import generate_id
from app.shared.domain.utils.timezone import (
    is_multi_tz_country,
    is_supported_country,
    resolve_timezone,
)
from app.shared.infrastructure.auth.jwt import create_access_token
from app.user.domain.exceptions.exceptions import UserEmailDuplicatedException
from app.user.domain.models.user import User
from app.user.domain.models.value_objects import Email
from app.user.domain.repositories.repository import IUserRepository


class CompleteOnboardingUseCase:
    def __init__(
        self,
        onboarding_cache: OnboardingTokenCache,
        user_repo: IUserRepository,
        oauth_connection_repo: IOAuthConnectionRepository,
        auth_token_cache: AuthTokenCache,
    ) -> None:
        self._onboarding_cache = onboarding_cache
        self._user_repo = user_repo
        self._oauth_connection_repo = oauth_connection_repo
        self._auth_token_cache = auth_token_cache

    async def execute(self, cmd: CompleteOnboardingCommand) -> dict[str, str]:
        if not is_supported_country(cmd.country):
            raise CountryInvalidException(f"Unsupported country: {cmd.country}")
        if is_multi_tz_country(cmd.country) and not cmd.region:
            raise CountryRegionRequiredException(
                f"Region required for {cmd.country}"
            )
        try:
            tz = resolve_timezone(cmd.country, cmd.region)
        except ValueError as e:
            raise CountryInvalidException(str(e))

        payload = await self._onboarding_cache.consume(cmd.onboarding_token)
        provider_str = payload["provider"]
        provider_user_id = payload["provider_user_id"]
        email = payload["email"]

        if await self._user_repo.find_by_email(email):
            raise UserEmailDuplicatedException()

        now = datetime.now(timezone.utc)
        user = User(
            id=generate_id("user"),
            email=Email(email),
            password_hash=None,
            country=cmd.country,
            region=cmd.region,
            timezone=tz,
            created_at=now,
        )
        saved = await self._user_repo.save(user)

        connection = OAuthConnection(
            id=generate_id("oauth"),
            user_id=saved.id,
            provider=OAuthProvider(provider_str),
            provider_user_id=provider_user_id,
            access_token="",  # provider 액세스 토큰은 onboarding 완료 후 별도 갱신 (재인증 흐름)
            created_at=now,
        )
        await self._oauth_connection_repo.save(connection)

        access_token = create_access_token(saved.id)
        raw_refresh = secrets.token_urlsafe(32)
        refresh_hash = hashlib.sha256(raw_refresh.encode()).hexdigest()
        await self._auth_token_cache.store(refresh_hash, saved.id, cmd.device_info)

        return {"access_token": access_token, "refresh_token": raw_refresh}
