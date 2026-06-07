from datetime import datetime, timezone

from app.auth.application.dtos.commands import CompleteOnboardingCommand
from app.auth.application.services.session_service import RequestMeta, SessionService
from app.auth.domain.exceptions.exceptions import (
    CountryInvalidException,
    CountryTimezoneRequiredException,
)
from app.auth.domain.models.oauth_connection import OAuthConnection
from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.domain.repositories.repository import IOAuthConnectionRepository
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
from app.user.domain.repositories.country_history_repository import (
    CountryChangeSource,
    ICountryHistoryRepository,
)
from app.user.domain.repositories.repository import IUserRepository


class CompleteOnboardingUseCase:
    def __init__(
        self,
        onboarding_cache: OnboardingTokenCache,
        user_repo: IUserRepository,
        oauth_connection_repo: IOAuthConnectionRepository,
        session_service: SessionService,
        country_history_repo: ICountryHistoryRepository,
    ) -> None:
        self._onboarding_cache = onboarding_cache
        self._user_repo = user_repo
        self._oauth_connection_repo = oauth_connection_repo
        self._session_service = session_service
        self._country_history_repo = country_history_repo

    async def execute(self, cmd: CompleteOnboardingCommand) -> dict[str, str]:
        if not is_supported_country(cmd.country):
            raise CountryInvalidException(f"Unsupported country: {cmd.country}")
        if is_multi_tz_country(cmd.country) and not cmd.timezone:
            raise CountryTimezoneRequiredException(
                f"Timezone required for multi-timezone country: {cmd.country}"
            )
        try:
            tz = resolve_timezone(cmd.country, cmd.timezone)
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
            region=None,
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

        await self._country_history_repo.record(
            user_id=saved.id,
            country=cmd.country,
            region=None,
            timezone=tz,
            source=CountryChangeSource.OAUTH_ONBOARDING,
            at=now,
        )

        issued = await self._session_service.issue(
            saved.id, RequestMeta(user_agent=cmd.device_info, ip=cmd.ip)
        )
        return {
            "access_token": create_access_token(saved.id),
            "refresh_token": issued.refresh_token,
        }
