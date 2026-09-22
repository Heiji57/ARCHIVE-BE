"""OAuth state 캐시.

state 페이로드는 dict 형태로 저장된다:
- 일반 로그인 흐름:  {"provider": "github"}
- 계정 link 흐름:    {"provider": "github", "link_user_id": "user_..."}
- 공통 선택 필드:    "api_version": "v2" — v2 authorize/link-init 으로 시작한 흐름

callback 처리기는 `link_user_id` 유무로 분기한다. callback URL 은 provider 에 등록된
redirect_uri 라 v1 경로에 고정이므로, 에러 코드 버전은 `api_version` 으로 판단한다.
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

    async def create_state(self, provider: str, api_version: str = "v1") -> str:
        """일반 로그인용 state — provider만 저장."""
        return await self._save({"provider": provider}, api_version)

    async def create_link_state(
        self, provider: str, user_id: str, api_version: str = "v1"
    ) -> str:
        """계정 link용 state — provider + 현재 user_id 저장."""
        return await self._save({"provider": provider, "link_user_id": user_id}, api_version)

    async def _save(self, payload: dict[str, str], api_version: str) -> str:
        state = secrets.token_urlsafe(32)
        if api_version != "v1":
            payload = {**payload, "api_version": api_version}
        await self._redis.setex(self._key(state), self._ttl, json.dumps(payload))
        return state

    async def peek_api_version(self, state: str) -> str:
        """state 를 소비하지 않고 흐름의 API 버전만 조회. 없거나 깨졌으면 v1."""
        raw = await self._redis.get(self._key(state))
        if not raw:
            return "v1"
        try:
            return str(json.loads(raw).get("api_version", "v1"))
        except (ValueError, AttributeError):
            return "v1"

    async def consume_state(self, state: str) -> dict[str, str]:
        """state를 1회용으로 소비. 반환 dict에 provider 항상 포함, link_user_id는 선택."""
        raw = await self._redis.getdel(self._key(state))
        if not raw:
            raise OAuthStateInvalidException()
        # 과거 형식(plain provider 문자열) 호환은 의도적으로 제거 — 캐시 짧은 TTL로 안전
        return json.loads(raw)
