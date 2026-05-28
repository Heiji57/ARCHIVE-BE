import secrets

from redis.asyncio import Redis

from app.auth.domain.exceptions.exceptions import OAuthStateInvalidException


class OAuthStateCache:
    _TTL = 600  # 10 minutes

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, state: str) -> str:
        return f"auth:oauth:state:{state}"

    async def create_state(self, provider: str) -> str:
        state = secrets.token_urlsafe(32)
        await self._redis.setex(self._key(state), self._TTL, provider)
        return state

    async def consume_state(self, state: str) -> str:
        provider = await self._redis.getdel(self._key(state))
        if not provider:
            raise OAuthStateInvalidException()
        return provider
