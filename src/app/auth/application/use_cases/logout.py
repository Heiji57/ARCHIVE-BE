import hashlib

from app.auth.infrastructure.cache.auth_token import AuthTokenCache


class LogoutUseCase:
    def __init__(self, auth_token_cache: AuthTokenCache) -> None:
        self._auth_token_cache = auth_token_cache

    async def execute(self, user_id: str, raw_refresh_token: str) -> None:
        token_hash = hashlib.sha256(raw_refresh_token.encode()).hexdigest()
        await self._auth_token_cache.revoke(token_hash, user_id)
