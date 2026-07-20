from datetime import datetime, timezone

from app.auth.application.dtos.commands import RegisterCommand
from app.auth.application.services.session_service import RequestMeta, SessionService
from app.auth.domain.exceptions.exceptions import (
    CountryInvalidException,
    CountryTimezoneRequiredException,
    EmailNotVerifiedException,
)
from app.auth.infrastructure.cache.email_verification import EmailVerificationCache
from app.retrospective.application.use_cases.seed_retro_templates import SeedRetroTemplatesUseCase
from app.shared.domain.utils.id import generate_id
from app.shared.domain.utils.timezone import (
    is_multi_tz_country,
    is_supported_country,
    resolve_timezone,
)
from app.shared.infrastructure.auth.jwt import create_access_token
from app.shared.infrastructure.auth.password import hash_password
from app.user.domain.exceptions.exceptions import UserEmailDuplicatedException
from app.user.domain.models.user import User
from app.user.domain.models.value_objects import Email
from app.user.domain.repositories.country_history_repository import (
    CountryChangeSource,
    ICountryHistoryRepository,
)
from app.user.domain.repositories.repository import IUserRepository


class RegisterUseCase:
    def __init__(
        self,
        user_repo: IUserRepository,
        verification_cache: EmailVerificationCache,
        session_service: SessionService,
        country_history_repo: ICountryHistoryRepository,
        seed_retro_templates: SeedRetroTemplatesUseCase,
    ) -> None:
        self._user_repo = user_repo
        self._verification_cache = verification_cache
        self._session_service = session_service
        self._country_history_repo = country_history_repo
        self._seed_retro_templates = seed_retro_templates

    async def execute(self, cmd: RegisterCommand) -> dict[str, str]:
        if not await self._verification_cache.is_verified(cmd.email):
            raise EmailNotVerifiedException("Email not verified.")

        if await self._user_repo.find_by_email(cmd.email):
            raise UserEmailDuplicatedException()

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

        now = datetime.now(timezone.utc)
        user = User(
            id=generate_id("user"),
            email=Email(cmd.email),
            password_hash=hash_password(cmd.password),
            country=cmd.country,
            region=None,
            timezone=tz,
            created_at=now,
        )
        saved = await self._user_repo.save(user)
        await self._verification_cache.consume_verified(cmd.email)

        await self._country_history_repo.record(
            user_id=saved.id,
            country=cmd.country,
            region=None,
            timezone=tz,
            source=CountryChangeSource.REGISTRATION,
            at=now,
        )

        await self._seed_retro_templates.execute(saved.id)

        issued = await self._session_service.issue(
            saved.id, RequestMeta(user_agent=cmd.device_info, ip=cmd.ip)
        )
        return {
            "access_token": create_access_token(saved.id, saved.account_type),
            "refresh_token": issued.refresh_token,
        }
