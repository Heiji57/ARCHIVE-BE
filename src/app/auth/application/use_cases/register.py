import hashlib
import secrets
from datetime import datetime, timezone

from app.auth.application.dtos.commands import RegisterCommand
from app.auth.infrastructure.cache.auth_token import AuthTokenCache
from app.auth.infrastructure.cache.email_verification import EmailVerificationCache
from app.shared.domain.utils.id import generate_id
from app.shared.infrastructure.auth.jwt import create_access_token
from app.shared.infrastructure.auth.password import hash_password
from app.user.domain.exceptions.exceptions import UserEmailDuplicatedException
from app.user.domain.models.user import User
from app.user.domain.models.value_objects import Email
from app.user.domain.repositories.repository import IUserRepository


class RegisterUseCase:
    def __init__(
        self,
        user_repo: IUserRepository,
        verification_cache: EmailVerificationCache,
        auth_token_cache: AuthTokenCache,
    ) -> None:
        self._user_repo = user_repo
        self._verification_cache = verification_cache
        self._auth_token_cache = auth_token_cache

    async def execute(self, cmd: RegisterCommand) -> dict[str, str]:
        if not await self._verification_cache.is_verified(cmd.email):
            from app.auth.domain.exceptions.exceptions import AuthTokenInvalidException
            raise AuthTokenInvalidException("Email not verified.")

        if await self._user_repo.find_by_email(cmd.email):
            raise UserEmailDuplicatedException()

        now = datetime.now(timezone.utc)
        user = User(
            id=generate_id("user"),
            email=Email(cmd.email),
            password_hash=hash_password(cmd.password),
            totp_enabled=False,
            totp_secret=None,
            created_at=now,
        )
        saved = await self._user_repo.save(user)
        await self._verification_cache.consume_verified(cmd.email)

        access_token = create_access_token(saved.id)
        raw_refresh = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_refresh.encode()).hexdigest()
        await self._auth_token_cache.store(token_hash, saved.id, cmd.device_info)

        return {"access_token": access_token, "refresh_token": raw_refresh}
