"""커밋 날짜별 캐시 (Redis).

키 `gh:commits:{user_id}:{sha1(scope)[:10]}:{repository_id}:{date_key}`.

캐시는 부가 수단이라 Redis 장애는 미스/무시로 흡수한다 — GitHub 조회는 계속된다.
"""

import hashlib
import json
from typing import Any

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.github.domain.repositories.repository import ICommitDayCache

_log = structlog.get_logger(__name__)
_PREFIX = "gh:commits"


def _key(user_id: str, scope: str, repository_id: str, date_key: str) -> str:
    digest = hashlib.sha1(scope.encode()).hexdigest()[:10]
    return f"{_PREFIX}:{user_id}:{digest}:{repository_id}:{date_key}"


class RedisCommitDayCache(ICommitDayCache):
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get_many(
        self, user_id: str, scope: str, keys: list[tuple[str, str]]
    ) -> dict[tuple[str, str], list[dict[str, Any]]]:
        if not keys:
            return {}
        try:
            raws = await self._redis.mget([_key(user_id, scope, r, d) for r, d in keys])
        except RedisError:
            _log.warning("github.commit_cache.get_failed", user_id=user_id, exc_info=True)
            return {}
        out: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for k, raw in zip(keys, raws, strict=True):
            if raw is None:
                continue
            try:
                value = json.loads(raw)
            except ValueError:
                continue  # 깨진 값은 미스로 — 다시 받아 덮어쓴다
            if isinstance(value, list):
                out[k] = value
        return out

    async def set_many(
        self,
        user_id: str,
        scope: str,
        values: dict[tuple[str, str], list[dict[str, Any]]],
        ttl_seconds: dict[tuple[str, str], int],
    ) -> None:
        if not values:
            return
        try:
            async with self._redis.pipeline(transaction=False) as pipe:
                for (repo_id, date_key), payload in values.items():
                    pipe.setex(
                        _key(user_id, scope, repo_id, date_key),
                        ttl_seconds[(repo_id, date_key)],
                        json.dumps(payload),
                    )
                await pipe.execute()
        except RedisError:
            _log.warning("github.commit_cache.set_failed", user_id=user_id, exc_info=True)

    async def invalidate_user(self, user_id: str) -> None:
        try:
            keys = [k async for k in self._redis.scan_iter(match=f"{_PREFIX}:{user_id}:*")]
            if keys:
                await self._redis.delete(*keys)
        except RedisError:
            _log.warning("github.commit_cache.invalidate_failed", user_id=user_id, exc_info=True)
