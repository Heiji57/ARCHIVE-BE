"""OAuth state 캐시.

state 페이로드는 dict 형태로 저장된다:
- 일반 로그인 흐름:  {"provider": "github"}
- 계정 link 흐름:    {"provider": "github", "link_user_id": "user_..."}

callback 처리기는 `link_user_id` 유무로 분기한다.
"""
import json
import secrets

from redis.asyncio import Redis

from app.auth.domain.exceptions.exceptions import OAuthStateInvalidException
from app.shared.infrastructure.config.auth import AuthConfig


class OAuthStateCache:
    def __init__(self, redis: Redis, config: AuthConfig) -> None:
        self._redis = redis
        self._ttl = config.oauth_state_ttl_seconds

    def _key(self, state: str) -> str:
        return f"auth:oauth:state:{state}"

    async def create_state(self, provider: str) -> str:
        """일반 로그인용 state — provider만 저장."""
        state = secrets.token_urlsafe(32)
        payload = json.dumps({"provider": provider})
        await self._redis.setex(self._key(state), self._ttl, payload)
        return state

    async def create_link_state(self, provider: str, user_id: str) -> str:
        """계정 link용 state — provider + 현재 user_id 저장."""
        state = secrets.token_urlsafe(32)
        payload = json.dumps({"provider": provider, "link_user_id": user_id})
        await self._redis.setex(self._key(state), self._ttl, payload)
        return state

    async def consume_state(self, state: str) -> dict[str, str]:
        """state를 1회용으로 소비. 반환 dict에 provider 항상 포함, link_user_id는 선택."""
        raw = await self._redis.getdel(self._key(state))
        if not raw:
            raise OAuthStateInvalidException()
        # 과거 형식(plain provider 문자열) 호환은 의도적으로 제거 — 캐시 짧은 TTL로 안전
        return json.loads(raw)
