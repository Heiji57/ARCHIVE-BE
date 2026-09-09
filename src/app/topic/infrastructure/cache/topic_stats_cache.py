"""토픽 매칭 결과 캐시.

매칭 1회 = Gemini 임베딩 API 왕복 + pgvector 검색 2회 + 엔티티 배치 조회 2회.
통계/소스/목록 3개 엔드포인트가 같은 매칭을 필요로 하므로 결과를 TTL 동안 공유한다.

캐시 미스 stampede 방지: 같은 topic 을 동시에 여러 요청(다른 탭, 중복 새로고침 등)이
미스하면 각자 임베딩 API + DB 를 중복 호출하게 된다. `lock()`/`wait_for()` 로
"한 요청만 계산하고 나머지는 그 결과를 기다렸다가 재사용" 하는 single-flight 패턴을
지원한다 — 실제로 락을 걸지 말지는 호출자(`TopicMatcher`)가 결정한다.
"""
import asyncio
import hashlib
import json
import time
from typing import Any

from redis.asyncio import Redis
from redis.asyncio.lock import Lock

_KEY_PREFIX = "topic:match"
_LOCK_KEY_PREFIX = "topic:match:lock"


class TopicStatsCache:
    def __init__(
        self,
        redis: Redis,
        ttl_seconds: int,
        lock_ttl_seconds: float,
        wait_poll_interval_seconds: float,
    ) -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._lock_ttl = lock_ttl_seconds
        self._wait_poll_interval = wait_poll_interval_seconds

    @staticmethod
    def _fingerprint(name: str, description: str) -> str:
        # PATCH /topics/{id} 로 이름·설명이 바뀌면 임베딩 쿼리 텍스트가 달라지므로,
        # topic_id 만으로 키를 잡으면 TTL 동안 수정 전 매칭 결과가 나간다. 해시를 포함
        # 하면 별도 무효화 없이 자동으로 갈린다. 캐시 키와 락 키가 같은 지문을 쓰므로
        # "지금 계산 중인 락"과 "그 결과가 쓰일 캐시 항목"이 항상 짝을 이룬다.
        return hashlib.sha1(f"{name}\x00{description}".encode()).hexdigest()[:12]

    def _key(self, topic_id: str, name: str, description: str) -> str:
        return f"{_KEY_PREFIX}:{topic_id}:{self._fingerprint(name, description)}"

    def _lock_key(self, topic_id: str, name: str, description: str) -> str:
        return f"{_LOCK_KEY_PREFIX}:{topic_id}:{self._fingerprint(name, description)}"

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

    def lock(self, topic_id: str, name: str, description: str) -> Lock:
        """이 topic 의 계산을 이번 요청이 전담하겠다는 락(아직 획득하지 않은 객체).

        TTL(`lock_ttl_seconds`)이 있어 보유자가 응답 없이 죽어도 다른 요청이 넘겨받을
        수 있다 — 무한정 남는 락은 없다.
        """
        return self._redis.lock(
            self._lock_key(topic_id, name, description), timeout=self._lock_ttl
        )

    async def wait_for(
        self, topic_id: str, name: str, description: str, timeout: float
    ) -> dict[str, Any] | None:
        """락을 못 얻은 요청이 보유자의 계산 결과(캐시 적재)를 기다린다.

        락 자체가 아니라 캐시를 폴링한다 — 보유자가 계산을 끝내고 캐시를 쓰는 순간이
        곧 "결과가 준비됐다"는 신호이고, 락 해제(release)와는 별개의 타이밍이다.
        `timeout` 안에 값이 나타나지 않으면 None — 보유자가 비정상 종료했다고 보고
        호출자가 직접 계산하도록 한다(안전망).
        """
        deadline = time.monotonic() + timeout
        while True:
            cached = await self.get(topic_id, name, description)
            if cached is not None:
                return cached
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            await asyncio.sleep(min(self._wait_poll_interval, remaining))
