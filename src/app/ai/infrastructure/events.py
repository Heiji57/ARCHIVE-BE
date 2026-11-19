"""대화 SSE 이벤트를 Redis pub/sub 으로 — 요약·주제 정리와 같은 패턴.

채널 `ai:conversation:{id}`.
"""

import json
from typing import Any

from redis.asyncio import Redis

CHANNEL = "ai:conversation:{conversation_id}"


class RedisEventSink:
    def __init__(self, redis: Redis, conversation_id: str) -> None:
        self._redis = redis
        self._channel = CHANNEL.format(conversation_id=conversation_id)

    async def emit(self, event: dict[str, Any]) -> None:
        await self._redis.publish(self._channel, json.dumps(event, ensure_ascii=False))


class CommitAwareSink:
    """진행 문장·답 글자는 바로, 제안은 **커밋 뒤** 보낸다.

    제안 행은 차례 트랜잭션 안에서 저장되므로, 먼저 보내면 FE 가 커밋 전에 조회·적용해 404 가
    나거나, 뒤이은 실패로 롤백된 "유령 제안"을 보게 된다.
    """

    def __init__(self, inner: RedisEventSink) -> None:
        self._inner = inner
        self._held: list[dict[str, Any]] = []

    async def emit(self, event: dict[str, Any]) -> None:
        if event.get("type") == "proposal":
            self._held.append(event)
        else:
            await self._inner.emit(event)

    async def flush(self) -> None:
        for event in self._held:
            await self._inner.emit(event)
        self._held.clear()

    def discard(self) -> None:
        self._held.clear()
