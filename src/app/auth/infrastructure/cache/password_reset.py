"""비밀번호 재설정 토큰 캐시.

흐름:
1. 사용자가 POST /auth/password/reset/request {email}
2. 서버는 (email이 존재 + 비밀번호 보유)할 때만 random token 생성 + Redis 저장
3. 이메일로 reset 링크 발송 (token 포함)
4. 사용자가 POST /auth/password/reset/confirm {token, newPassword}
5. 서버는 Redis 조회 → user_id 획득 → 비밀번호 갱신 + 토큰 consume
6. 모든 refresh token 폐기 (강제 재로그인)

이메일 존재 여부를 응답에서 누설하지 않기 위해 step 1은 항상 200 반환.
"""
import secrets

from redis.asyncio import Redis

from app.auth.domain.exceptions.exceptions import PasswordResetTokenExpiredException


class PasswordResetCache:
    _TTL = 1800  # 30 minutes
    _COOLDOWN_TTL = 60  # 재발송 쿨다운

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key_token(self, token: str) -> str:
        return f"auth:pwreset:{token}"

    def _key_cooldown(self, email: str) -> str:
        return f"auth:pwreset:cooldown:{email}"

    async def is_on_cooldown(self, email: str) -> bool:
        return bool(await self._redis.exists(self._key_cooldown(email)))

    async def create_token(self, user_id: str, email: str) -> str:
        token = secrets.token_urlsafe(32)
        await self._redis.setex(self._key_token(token), self._TTL, user_id)
        await self._redis.setex(self._key_cooldown(email), self._COOLDOWN_TTL, "1")
        return token

    async def consume_token(self, token: str) -> str:
        """토큰을 1회용으로 소비하고 user_id 반환."""
        user_id = await self._redis.getdel(self._key_token(token))
        if not user_id:
            raise PasswordResetTokenExpiredException()
        return user_id
