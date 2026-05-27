import json

from redis.asyncio import Redis

from app.shared.infrastructure.config.auth import AuthConfig


class AuthTokenCache:
    def __init__(self, redis: Redis, config: AuthConfig) -> None:
        self._redis = redis
        self._refresh_ttl = config.refresh_token_expire_days * 86400

    def _key_token(self, token_hash: str) -> str:
        return f"auth:refresh:{token_hash}"

    def _key_sessions(self, user_id: str) -> str:
        return f"auth:sessions:{user_id}"

    async def store(
        self, token_hash: str, user_id: str, device_info: str | None
    ) -> None:
        payload = json.dumps({"user_id": user_id, "device_info": device_info})
        await self._redis.setex(self._key_token(token_hash), self._refresh_ttl, payload)
        await self._redis.sadd(self._key_sessions(user_id), token_hash)

    async def get_user_id(self, token_hash: str) -> str | None:
        raw = await self._redis.get(self._key_token(token_hash))
        if not raw:
            return None
        return json.loads(raw)["user_id"]

    async def rotate(
        self,
        old_hash: str,
        new_hash: str,
        user_id: str,
        device_info: str | None,
    ) -> None:
        await self._redis.delete(self._key_token(old_hash))
        await self._redis.srem(self._key_sessions(user_id), old_hash)
        await self.store(new_hash, user_id, device_info)

    async def revoke(self, token_hash: str, user_id: str) -> None:
        await self._redis.delete(self._key_token(token_hash))
        await self._redis.srem(self._key_sessions(user_id), token_hash)

    async def revoke_all(self, user_id: str) -> None:
        hashes = await self._redis.smembers(self._key_sessions(user_id))
        if hashes:
            await self._redis.delete(*[self._key_token(h) for h in hashes])
        await self._redis.delete(self._key_sessions(user_id))
