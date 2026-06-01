import hashlib
import secrets

from app.auth.application.dtos.commands import LoginCommand
from app.auth.domain.exceptions.exceptions import AuthInvalidCredentialsException
from app.auth.infrastructure.cache.auth_token import AuthTokenCache
from app.shared.infrastructure.auth.jwt import create_access_token
from app.shared.infrastructure.auth.password import verify_password
from app.user.domain.repositories.repository import IUserRepository


class LoginUseCase:
    def __init__(
        self,
        user_repo: IUserRepository,
        auth_token_cache: AuthTokenCache,
    ) -> None:
        self._user_repo = user_repo
        self._auth_token_cache = auth_token_cache

    async def execute(self, cmd: LoginCommand) -> dict[str, str]:
        user = await self._user_repo.find_by_email(cmd.email)
        if not user or not user.password_hash:
            raise AuthInvalidCredentialsException()

        if not verify_password(cmd.password, user.password_hash):
            raise AuthInvalidCredentialsException()

        access_token = create_access_token(user.id)
        raw_refresh = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_refresh.encode()).hexdigest()
        await self._auth_token_cache.store(token_hash, user.id, cmd.device_info)

        return {"access_token": access_token, "refresh_token": raw_refresh}
