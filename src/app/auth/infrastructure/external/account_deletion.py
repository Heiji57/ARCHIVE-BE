"""계정 삭제의 바깥 부분 — 남은 access token 표식(Redis), 외부 토큰 철회 작업 넘기기."""

import json
import secrets

from redis.asyncio import Redis

from app.auth.application.ports import ExternalToken
from app.shared.infrastructure.auth.jwt import DELETED_USER_KEY

# 철회할 토큰은 Celery 인자(브로커·결과 저장소에 남는다)로 넘기지 않고 짧은 TTL Redis 키에 두고
# 키만 넘긴다. 워커가 다 철회하면 지운다. 재시도가 끝나도 TTL 이 지나면 사라진다.
REVOKE_TOKENS_KEY = "revoke_tokens:{ref}"
REVOKE_TOKENS_TTL_SECONDS = 3600


class RedisDeletedAccountMarker:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    async def mark(self, user_id: str) -> None:
        await self._redis.set(DELETED_USER_KEY.format(user_id=user_id), "1", ex=self._ttl)


class CeleryTokenRevoker:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def enqueue(self, tokens: list[ExternalToken]) -> None:
        from app.worker.tasks.account_cleanup import revoke_account_tokens_task

        ref = secrets.token_urlsafe(18)
        payload = [{"provider": t.provider, "token": t.token} for t in tokens]
        await self._redis.set(
            REVOKE_TOKENS_KEY.format(ref=ref), json.dumps(payload), ex=REVOKE_TOKENS_TTL_SECONDS
        )
        revoke_account_tokens_task.apply_async(args=[ref], queue="default")
