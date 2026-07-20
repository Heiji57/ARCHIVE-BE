"""Google Calendar 연결 OAuth state 캐시.

로그인 OAuth(`auth.OAuthStateCache`)와 분리 — 캘린더 연결은 항상 인증된 사용자가
시작하므로 state 에 `user_id` 를 담아 callback 에서 어느 사용자의 연결인지 식별한다.
CSRF 방어 + 1회용 소비.
"""
import json
import secrets

from redis.asyncio import Redis

from app.google_calendar.domain.exceptions.exceptions import (
    CalendarStateInvalidException,
)


class CalendarOAuthStateCache:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    def _key(self, state: str) -> str:
        return f"calendar:oauth:state:{state}"

    async def create_state(self, user_id: str) -> str:
        state = secrets.token_urlsafe(32)
        payload = json.dumps({"user_id": user_id})
        await self._redis.setex(self._key(state), self._ttl, payload)
        return state

    async def consume_state(self, state: str) -> str:
        """state 를 1회용으로 소비하고 user_id 반환."""
        raw = await self._redis.getdel(self._key(state))
        if not raw:
            raise CalendarStateInvalidException()
        return json.loads(raw)["user_id"]
