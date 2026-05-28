import hashlib
import secrets

from app.auth.domain.exceptions.exceptions import RefreshTokenInvalidException
from app.auth.infrastructure.cache.auth_token import AuthTokenCache
from app.shared.infrastructure.auth.jwt import create_access_token
from app.user.domain.repositories.repository import IUserRepository


class RefreshTokenUseCase:
    def __init__(
        self,
        user_repo: IUserRepository,
        auth_token_cache: AuthTokenCache,
    ) -> None:
        self._user_repo = user_repo
        self._auth_token_cache = auth_token_cache

    async def execute(
        self, raw_refresh_token: str, device_info: str | None
    ) -> dict[str, str]:
        old_hash = hashlib.sha256(raw_refresh_token.encode()).hexdigest()
        user_id = await self._auth_token_cache.get_user_id(old_hash)
        if not user_id:
            raise RefreshTokenInvalidException()

        raw_new = secrets.token_urlsafe(32)
        new_hash = hashlib.sha256(raw_new.encode()).hexdigest()
        await self._auth_token_cache.rotate(old_hash, new_hash, user_id, device_info)

        return {
            "access_token": create_access_token(user_id),
            "refresh_token": raw_new,
        }
