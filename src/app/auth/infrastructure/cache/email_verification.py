import json
import secrets

from redis.asyncio import Redis

from app.auth.domain.exceptions.exceptions import AuthTokenInvalidException
from app.shared.infrastructure.config.auth import AuthConfig


class EmailVerificationCache:
    def __init__(self, redis: Redis, config: AuthConfig) -> None:
        self._redis = redis
        self._verify_ttl = config.email_verify_code_ttl_seconds
        self._verified_ttl = config.email_verified_ttl_seconds
        self._cooldown_ttl = config.email_cooldown_ttl_seconds
        self._max_attempts = config.email_max_verify_attempts

    def _key_code(self, email: str) -> str:
        return f"auth:email:verify:{email}"

    def _key_verified(self, email: str) -> str:
        return f"auth:email:verified:{email}"

    def _key_cooldown(self, email: str) -> str:
        return f"auth:email:cooldown:{email}"

    async def is_on_cooldown(self, email: str) -> bool:
        return bool(await self._redis.exists(self._key_cooldown(email)))

    async def create_code(self, email: str) -> str:
        code = f"{secrets.randbelow(1_000_000):06d}"
        payload = json.dumps({"code": code, "attempts": 0})
        await self._redis.setex(self._key_code(email), self._verify_ttl, payload)
        await self._redis.setex(self._key_cooldown(email), self._cooldown_ttl, "1")
        return code

    async def verify_code(self, email: str, code: str) -> None:
        raw = await self._redis.get(self._key_code(email))
        if not raw:
            raise AuthTokenInvalidException("Verification code expired or not found.")

        data = json.loads(raw)
        if data["attempts"] >= self._max_attempts:
            await self._redis.delete(self._key_code(email))
            raise AuthTokenInvalidException("Too many attempts. Please request a new code.")

        if data["code"] != code:
            data["attempts"] += 1
            await self._redis.setex(
                self._key_code(email),
                self._verify_ttl,
                json.dumps(data),
            )
            raise AuthTokenInvalidException("Invalid verification code.")

        await self._redis.delete(self._key_code(email))
        await self._redis.setex(self._key_verified(email), self._verified_ttl, "1")

    async def is_verified(self, email: str) -> bool:
        return bool(await self._redis.exists(self._key_verified(email)))

    async def consume_verified(self, email: str) -> None:
        await self._redis.delete(self._key_verified(email))
