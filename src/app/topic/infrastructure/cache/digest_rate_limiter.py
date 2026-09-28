"""사용자별 주제 정리 생성 횟수 제한 (Redis sliding window).

주제 정리는 AI 1회 호출이 가장 비싼 경로인데 요약과 달리 한도가 없어, 연타·악용 시
비용이 상한 없이 쌓였다. 구현은 요약 한도(`retrospective/infrastructure/cache/
summary_rate_limiter.py`)와 같은 Sorted Set 방식 — 조회와 기록 사이의 race 는 같은
이유(사용자 1회 액션 = 1회 호출)로 pipeline 으로 충분하다고 본다.
"""
import time
import uuid

from redis.asyncio import Redis

from app.topic.domain.exceptions.exceptions import DigestRateLimitExceededException
from app.topic.domain.repositories.repository import IDigestRateLimiter


class DigestRateLimiter(IDigestRateLimiter):
    def __init__(self, redis: Redis, limit: int, window_seconds: int) -> None:
        self._redis = redis
        self._limit = limit
        self._window = window_seconds

    @staticmethod
    def _key(user_id: str) -> str:
        return f"topic:digest:usage:{user_id}"

    async def check_and_record(self, user_id: str) -> None:
        key = self._key(user_id)
        now = time.time()

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, now - self._window)
        pipe.zcard(key)
        pipe.zrange(key, 0, 0, withscores=True)
        _, used, oldest = await pipe.execute()

        if used >= self._limit:
            retry_after = 0
            if oldest:
                retry_after = max(0, int(oldest[0][1] + self._window - now) + 1)
            raise DigestRateLimitExceededException(
                limit=self._limit,
                window_seconds=self._window,
                retry_after_seconds=retry_after,
            )

        pipe = self._redis.pipeline()
        pipe.zadd(key, {f"{now}:{uuid.uuid4().hex}": now})
        pipe.expire(key, self._window + 24 * 3600)
        await pipe.execute()
