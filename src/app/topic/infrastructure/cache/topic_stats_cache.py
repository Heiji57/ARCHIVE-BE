"""토픽 매칭 결과 캐시.

매칭 1회 = Gemini 임베딩 API 왕복 + pgvector 검색 2회 + 엔티티 배치 조회 2회.
통계/소스/목록 3개 엔드포인트가 같은 매칭을 필요로 하므로 결과를 TTL 동안 공유한다.
"""
import hashlib
import json
from typing import Any

from redis.asyncio import Redis

_KEY_PREFIX = "topic:match"


class TopicStatsCache:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    @staticmethod
    def _key(topic_id: str, name: str, description: str) -> str:
        # name/description 을 키에 섞는다 — PATCH /topics/{id} 로 이름·설명이 바뀌면
        # 임베딩 쿼리 텍스트가 달라지므로, topic_id 만으로 키를 잡으면 TTL 동안 수정 전
        # 매칭 결과가 나간다. 해시를 포함하면 별도 무효화 없이 자동으로 갈린다.
        fingerprint = hashlib.sha1(f"{name}\x00{description}".encode()).hexdigest()[:12]
        return f"{_KEY_PREFIX}:{topic_id}:{fingerprint}"

    async def get(self, topic_id: str, name: str, description: str) -> dict[str, Any] | None:
        raw = await self._redis.get(self._key(topic_id, name, description))
        return json.loads(raw) if raw else None

    async def set(
        self, topic_id: str, name: str, description: str, payload: dict[str, Any]
    ) -> None:
        await self._redis.set(
            self._key(topic_id, name, description),
            json.dumps(payload),
            ex=self._ttl,
        )
