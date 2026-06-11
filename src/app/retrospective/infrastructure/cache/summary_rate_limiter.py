"""사용자별 AI 요약 생성 요청 횟수 제한 (Redis sliding window).

한도 (7일 rolling window):
- WEEKLY  : 10
- MONTHLY :  3
- ANNUAL  :  1

카운트 시점: 실제로 AI 호출이 enqueue 되는 경로에서만.
- COMPLETED + force=False (그대로 반환) → 카운트 안 함
- PENDING/IN_PROGRESS 충돌 (409) → 카운트 안 함
- FAILED 재시도 / COMPLETED + force=True / 신규 → 카운트 +1

구현: Redis Sorted Set. score=unix_ts(ms), member=unique_id(summary_id).
원자성은 pipeline 으로 보장. 결과 조회와 record 가 별도면 race 가능하지만,
- AI 호출은 사용자 액션 1회당 1번만 발생 (FE 가 중복 클릭 방지)
- 한 사용자가 동시 다발 요청을 보내는 시나리오는 비현실적
→ pipeline 으로 충분 (Lua 까지 안 가도 됨).

key TTL = window + 1일 (자동 정리).
"""
import time
import uuid
from dataclasses import dataclass

from redis.asyncio import Redis

from app.retrospective.domain.exceptions.exceptions import (
    SummaryRateLimitExceededException,
)
from app.retrospective.domain.models.value_objects import SummaryType

SUMMARY_RATE_LIMITS: dict[SummaryType, int] = {
    SummaryType.WEEKLY: 10,
    SummaryType.MONTHLY: 3,
    SummaryType.ANNUAL: 1,
}
SUMMARY_RATE_WINDOW_SECONDS = 7 * 24 * 3600
_KEY_TTL_SECONDS = SUMMARY_RATE_WINDOW_SECONDS + 24 * 3600


@dataclass(frozen=True)
class UsageState:
    summary_type: SummaryType
    used: int
    limit: int
    window_seconds: int
    retry_after_seconds: int  # 남은 한도 있으면 0, 없으면 가장 오래된 기록이 빠지는 시각까지의 초


class SummaryRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, user_id: str, summary_type: SummaryType) -> str:
        return f"summary:usage:{user_id}:{summary_type.value}"

    async def get_usage(
        self, user_id: str, summary_type: SummaryType
    ) -> UsageState:
        """현재 사용량 조회 (record 하지 않음). usage API 용."""
        key = self._key(user_id, summary_type)
        limit = SUMMARY_RATE_LIMITS[summary_type]
        now = time.time()
        cutoff = now - SUMMARY_RATE_WINDOW_SECONDS

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zcard(key)
        pipe.zrange(key, 0, 0, withscores=True)  # 가장 오래된 항목 1개
        _, used, oldest = await pipe.execute()

        retry_after = 0
        if used >= limit and oldest:
            oldest_score = oldest[0][1]
            retry_after = max(0, int(oldest_score + SUMMARY_RATE_WINDOW_SECONDS - now) + 1)

        return UsageState(
            summary_type=summary_type,
            used=int(used),
            limit=limit,
            window_seconds=SUMMARY_RATE_WINDOW_SECONDS,
            retry_after_seconds=retry_after,
        )

    async def check_and_record(
        self, user_id: str, summary_type: SummaryType
    ) -> None:
        """한도 검사 + 사용량 기록. 한도 초과 시 SummaryRateLimitExceededException raise.

        AI 호출이 실제로 발생하는 경로에서만 호출해야 함.
        """
        usage = await self.get_usage(user_id, summary_type)
        if usage.used >= usage.limit:
            raise SummaryRateLimitExceededException(
                summary_type=summary_type.value,
                limit=usage.limit,
                window_seconds=usage.window_seconds,
                retry_after_seconds=usage.retry_after_seconds,
            )

        key = self._key(user_id, summary_type)
        now = time.time()
        member = f"{now}:{uuid.uuid4().hex}"

        pipe = self._redis.pipeline()
        pipe.zadd(key, {member: now})
        pipe.expire(key, _KEY_TTL_SECONDS)
        await pipe.execute()
