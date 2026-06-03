"""OAuth 신규 사용자 온보딩 임시 토큰 캐시.

흐름:
1. OAuth provider 토큰 교환 + user_info 조회 성공
2. 기존 가입자 없음 확인 → onboarding_token 발급
3. Redis에 provider/provider_user_id/email/name TTL 30분으로 저장
4. HttpOnly cookie로 클라이언트에 token 전달, /onboarding 페이지로 redirect
5. FE가 국가 정보 + token으로 POST /auth/oauth/onboarding 호출
6. Redis 조회 → 정보 가져오기 → 계정 생성 → 토큰 제거
"""
import json
import secrets

from redis.asyncio import Redis

from app.auth.domain.exceptions.exceptions import OnboardingTokenExpiredException


class OnboardingTokenCache:
    _TTL = 1800  # 30 minutes

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, token: str) -> str:
        return f"auth:onboarding:{token}"

    async def create(
        self,
        provider: str,
        provider_user_id: str,
        email: str,
    ) -> str:
        token = secrets.token_urlsafe(32)
        payload = json.dumps({
            "provider": provider,
            "provider_user_id": provider_user_id,
            "email": email,
        })
        await self._redis.setex(self._key(token), self._TTL, payload)
        return token

    async def peek(self, token: str) -> dict[str, str]:
        raw = await self._redis.get(self._key(token))
        if not raw:
            raise OnboardingTokenExpiredException()
        return json.loads(raw)

    async def consume(self, token: str) -> dict[str, str]:
        raw = await self._redis.getdel(self._key(token))
        if not raw:
            raise OnboardingTokenExpiredException()
        return json.loads(raw)
