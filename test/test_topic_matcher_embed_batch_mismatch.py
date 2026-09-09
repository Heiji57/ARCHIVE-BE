"""TopicMatcher.match_many — embed_batch 가 부분 응답을 돌려줄 때의 동작.

GitHub #3: `zip(batch, embeddings)` 에 `strict=` 가 없어, 임베딩 API 가 입력보다 적은
벡터를 돌려주면 뒤쪽 주제들이 `matches` 에서 조용히 빠졌다. `GET /topics` 목록은
`GetTopicsUseCase` 의 넓은 except 로 감싸져 있어 카운트가 null 로 degrade 됐지만,
`match()`(단일 토픽, `/stats`·`/sources` 가 사용)는 `result[topic.id]` 에서 원인을 알 수
없는 `KeyError` → 에러 코드 없는 500 이 났다.

수정: `zip(..., strict=True)` 로 배치를 원자적으로 실패시킨다. 부분 응답은 총 실패와
같은 경로(전파)를 타게 되어, 이미 오늘도 존재하는 "임베딩 API 총 실패 시 그대로
전파된다"는 동작과 일관돼진다.
"""
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from app.shared.infrastructure.config.topic import TopicConfig
from app.topic.application.services.topic_matcher import TopicMatcher
from app.topic.domain.models.topic import Topic

_NOW = datetime.now(UTC)


class _EmptyVectorRepo:
    """chunk_repo / todo_emb_repo 대역 — 매칭 로직 자체는 이 테스트의 관심사가 아니다."""

    async def search_similar(self, **kwargs):
        return []


class _EmptyEntityRepo:
    async def find_by_ids(self, user_id, ids):
        return []


class _NoOpAsyncContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _NoOpTransaction:
    """ITopicMatchTransaction 대역 — 이 테스트는 SAVEPOINT 자체가 아니라 zip 배선을
    검증하므로, 아무것도 하지 않는 async 컨텍스트만 있으면 된다."""

    def nested(self):
        return _NoOpAsyncContext()


class _AlwaysAcquiredLock:
    """cache stampede 락 대역 — 경합 없는 단일 요청 시나리오라 항상 즉시 획득된다."""

    async def acquire(self, blocking: bool = True) -> bool:
        return True

    async def release(self) -> None:
        pass


@dataclass
class _NoOpCache:
    """항상 미스 — embed_batch 경로를 매번 타게 한다. 락은 항상 즉시 획득된다."""

    store: dict = field(default_factory=dict)

    async def get(self, topic_id, name, description):
        return None

    async def set(self, topic_id, name, description, payload):
        self.store[topic_id] = payload

    def lock(self, topic_id, name, description):
        return _AlwaysAcquiredLock()

    async def wait_for(self, topic_id, name, description, timeout):
        return None


class _ShortEmbeddingService:
    """요청보다 적은 벡터를 돌려주는 임베딩 API 대역 — 부분 실패/조기 종료를 흉내낸다."""

    def __init__(self, n: int) -> None:
        self._n = n

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 4 for _ in range(min(self._n, len(texts)))]


def _topic(tid: str) -> Topic:
    return Topic(id=tid, user_id="u1", name=f"주제 {tid}", description="", created_at=_NOW)


def _matcher(embedding_service) -> TopicMatcher:
    return TopicMatcher(
        embedding_service=embedding_service,
        chunk_repo=_EmptyVectorRepo(),
        todo_emb_repo=_EmptyVectorRepo(),
        entry_repo=_EmptyEntityRepo(),
        todo_repo=_EmptyEntityRepo(),
        cache=_NoOpCache(),
        config=TopicConfig(),
        transaction=_NoOpTransaction(),
    )


async def test_match_many_fails_atomically_on_partial_embedding_response() -> None:
    """3개 요청에 2개만 돌아오면 batch 전체가 실패해야 한다 — 일부만 채워지면 안 된다."""
    matcher = _matcher(_ShortEmbeddingService(n=2))
    topics = [_topic("t1"), _topic("t2"), _topic("t3")]

    with pytest.raises(ValueError):
        await matcher.match_many("u1", topics)


async def test_match_raises_clear_error_instead_of_bare_keyerror() -> None:
    """단일 토픽 조회(/stats, /sources 경로)에서 원인 불명 KeyError 대신 명확히 실패한다."""
    matcher = _matcher(_ShortEmbeddingService(n=0))
    topic = _topic("t1")

    with pytest.raises(ValueError) as exc_info:
        await matcher.match(user_id="u1", topic=topic)

    assert not isinstance(exc_info.value, KeyError)


async def test_match_many_succeeds_when_embedding_count_matches() -> None:
    """정상 응답(길이 일치)에서는 여전히 문제없이 동작해야 한다 — 회귀 방지."""
    matcher = _matcher(_ShortEmbeddingService(n=3))
    topics = [_topic("t1"), _topic("t2"), _topic("t3")]

    matches = await matcher.match_many("u1", topics)

    assert set(matches.keys()) == {"t1", "t2", "t3"}
