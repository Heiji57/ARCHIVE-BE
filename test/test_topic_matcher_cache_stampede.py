"""TopicMatcher.match_many — cache miss 시 stampede 방지(single-flight) 동작.

GitHub #5: GET /topics 캐시 미스가 topic 당 벡터 검색 2회 + find_by_ids 2회(최대 2000
엔티티)를 태운다. 같은 topic 을 동시에 여러 요청(다른 탭, 중복 새로고침 등)이 미스하면
이 비용이 그대로 중복된다. `TopicStatsCache.lock()`/`wait_for()` 로 한 요청만 계산하고
(single-flight) 나머지는 그 결과를 기다렸다가 재사용하도록 했다.

이 테스트는 `TopicStatsCache`(Redis 래퍼) 자체가 아니라 `TopicMatcher.match_many` 의
분기 로직을 검증한다 — 락 획득/대기/폴백의 세 갈래가 실제로 올바른 부수효과(임베딩
호출 종류, 캐시 쓰기, 락 해제)를 낸다는 것.
"""
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from app.shared.infrastructure.config.topic import TopicConfig
from app.topic.application.services.topic_matcher import TopicMatcher
from app.topic.domain.models.topic import Topic

_NOW = datetime.now(UTC)


class _EmptyVectorRepo:
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
    def nested(self):
        return _NoOpAsyncContext()


@dataclass
class _FakeLock:
    acquire_result: bool
    raise_on_acquire: bool = False
    raise_on_release: bool = False
    acquired: bool = False
    released: bool = False
    release_attempts: int = 0

    async def acquire(self, blocking: bool = True) -> bool:
        if self.raise_on_acquire:
            raise ConnectionError("redis unavailable")
        self.acquired = self.acquire_result
        return self.acquire_result

    async def release(self) -> None:
        self.release_attempts += 1
        if self.raise_on_release:
            raise RuntimeError("LockNotOwnedError: TTL 만료로 이미 풀림")
        self.released = True


@dataclass
class _FakeCache:
    """topic_id 별로 락 획득 성공 여부와 wait_for 결과를 미리 정해 둘 수 있다."""

    lock_results: dict[str, bool] = field(default_factory=dict)
    raise_on_acquire: set[str] = field(default_factory=set)
    raise_on_release: set[str] = field(default_factory=set)
    wait_results: dict[str, dict | None] = field(default_factory=dict)
    store: dict[str, dict] = field(default_factory=dict)
    locks_issued: dict[str, _FakeLock] = field(default_factory=dict)
    wait_calls: list[str] = field(default_factory=list)

    async def get(self, topic_id, name, description):
        return self.store.get(topic_id)

    async def set(self, topic_id, name, description, payload):
        self.store[topic_id] = payload

    def lock(self, topic_id, name, description) -> _FakeLock:
        fake_lock = _FakeLock(
            acquire_result=self.lock_results.get(topic_id, True),
            raise_on_acquire=topic_id in self.raise_on_acquire,
            raise_on_release=topic_id in self.raise_on_release,
        )
        self.locks_issued[topic_id] = fake_lock
        return fake_lock

    async def wait_for(self, topic_id, name, description, timeout):
        self.wait_calls.append(topic_id)
        return self.wait_results.get(topic_id)


class _TrackingEmbeddingService:
    def __init__(self) -> None:
        self.batch_calls: list[list[str]] = []
        self.single_calls: list[str] = []

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.batch_calls.append(list(texts))
        return [[0.1] * 4 for _ in texts]

    async def embed_text(self, text: str) -> list[float]:
        self.single_calls.append(text)
        return [0.1] * 4


def _topic(tid: str) -> Topic:
    return Topic(id=tid, user_id="u1", name=f"주제 {tid}", description="", created_at=_NOW)


def _matcher(cache: _FakeCache, embedding_service: _TrackingEmbeddingService) -> TopicMatcher:
    return TopicMatcher(
        embedding_service=embedding_service,
        chunk_repo=_EmptyVectorRepo(),
        todo_emb_repo=_EmptyVectorRepo(),
        entry_repo=_EmptyEntityRepo(),
        todo_repo=_EmptyEntityRepo(),
        cache=cache,
        config=TopicConfig(),
        transaction=_NoOpTransaction(),
    )


async def test_lock_acquired_computes_via_batch_and_releases_lock() -> None:
    """경합 없음 — 기존과 동일하게 embed_batch 로 한 번에 처리하고, 락은 반드시 해제한다."""
    cache = _FakeCache(lock_results={"t1": True, "t2": True})
    embedding_service = _TrackingEmbeddingService()
    matcher = _matcher(cache, embedding_service)

    matches = await matcher.match_many("u1", [_topic("t1"), _topic("t2")])

    assert set(matches.keys()) == {"t1", "t2"}
    assert embedding_service.batch_calls == [["주제 t1", "주제 t2"]], (
        "여러 topic 을 한 번에 임베딩해야 한다"
    )
    assert embedding_service.single_calls == []
    assert cache.locks_issued["t1"].released
    assert cache.locks_issued["t2"].released
    assert cache.wait_calls == [], "락을 얻었으면 기다릴 필요가 없다"


async def test_lock_contended_and_holder_finishes_reuses_cached_result_no_recompute() -> None:
    """다른 요청이 락을 쥐고 있다가 제때 끝내면, 이번 요청은 재계산 없이 그 결과를 쓴다."""
    cache = _FakeCache(
        lock_results={"t1": False},
        wait_results={"t1": {"entries": [], "todos": []}},
    )
    embedding_service = _TrackingEmbeddingService()
    matcher = _matcher(cache, embedding_service)

    matches = await matcher.match_many("u1", [_topic("t1")])

    assert "t1" in matches
    assert embedding_service.batch_calls == [], "락을 못 얻었으면 임베딩을 호출하면 안 된다"
    assert embedding_service.single_calls == []
    assert cache.wait_calls == ["t1"]
    assert "t1" not in cache.locks_issued or not cache.locks_issued["t1"].released, (
        "락을 획득하지 못했으므로 release() 를 부를 이유가 없다"
    )


async def test_lock_contended_and_holder_times_out_falls_back_to_direct_compute() -> None:
    """보유자가 타임아웃 안에 못 끝내면(크래시 등) 락 없이 직접 계산해 안전망 역할을 한다."""
    cache = _FakeCache(lock_results={"t1": False}, wait_results={"t1": None})
    embedding_service = _TrackingEmbeddingService()
    matcher = _matcher(cache, embedding_service)

    matches = await matcher.match_many("u1", [_topic("t1")])

    assert "t1" in matches
    assert embedding_service.single_calls == ["주제 t1"], "폴백은 단건 embed_text 로 계산해야 한다"
    assert embedding_service.batch_calls == []
    assert cache.store.get("t1") is not None, "폴백 계산 결과도 다음 요청을 위해 캐시에 남겨야 한다"


async def test_lock_released_even_when_resolve_raises() -> None:
    """계산 중 실패해도 락이 새지 않아야 한다 — 안 그러면 TTL 만료까지 다른 요청이 막힌다."""

    class _FailingVectorRepo:
        async def search_similar(self, **kwargs):
            raise RuntimeError("db down")

    cache = _FakeCache(lock_results={"t1": True})
    embedding_service = _TrackingEmbeddingService()
    matcher = TopicMatcher(
        embedding_service=embedding_service,
        chunk_repo=_FailingVectorRepo(),
        todo_emb_repo=_EmptyVectorRepo(),
        entry_repo=_EmptyEntityRepo(),
        todo_repo=_EmptyEntityRepo(),
        cache=cache,
        config=TopicConfig(),
        transaction=_NoOpTransaction(),
    )

    with pytest.raises(RuntimeError):
        await matcher.match_many("u1", [_topic("t1")])

    assert cache.locks_issued["t1"].released, "실패해도 finally 에서 락을 해제해야 한다"


async def test_locks_acquired_before_a_later_acquire_failure_are_still_released() -> None:
    """락 "획득 시도" 자체가 도중에 실패해도(예: Redis 커넥션 오류), 이미 얻어 둔
    락은 finally 를 못 타고 새면 안 된다 — 그 finally 는 이 획득 루프 뒤에 있다."""
    cache = _FakeCache(lock_results={"t1": True}, raise_on_acquire={"t2"})
    embedding_service = _TrackingEmbeddingService()
    matcher = _matcher(cache, embedding_service)

    with pytest.raises(ConnectionError):
        await matcher.match_many("u1", [_topic("t1"), _topic("t2")])

    assert cache.locks_issued["t1"].released, "t2 획득 실패 이전에 t1 이 얻은 락이 새면 안 된다"
    assert not cache.locks_issued["t2"].released, "애초에 획득 못 한 락은 release 대상이 아니다"
    assert embedding_service.batch_calls == [], "락 획득 단계 실패면 임베딩 호출까지 가면 안 된다"


async def test_release_failure_for_one_lock_does_not_block_others_or_mask_original_error() -> None:
    """release() 가 하나 실패해도(TTL 만료로 이미 풀린 경우 등) 나머지는 마저 풀리고,
    원래 실패 원인(예: DB 오류)이 release 실패로 가려지면 안 된다."""

    class _FailingVectorRepo:
        async def search_similar(self, **kwargs):
            raise RuntimeError("db down")

    cache = _FakeCache(lock_results={"t1": True, "t2": True}, raise_on_release={"t1"})
    embedding_service = _TrackingEmbeddingService()
    matcher = TopicMatcher(
        embedding_service=embedding_service,
        chunk_repo=_FailingVectorRepo(),
        todo_emb_repo=_EmptyVectorRepo(),
        entry_repo=_EmptyEntityRepo(),
        todo_repo=_EmptyEntityRepo(),
        cache=cache,
        config=TopicConfig(),
        transaction=_NoOpTransaction(),
    )

    with pytest.raises(RuntimeError, match="db down"):
        await matcher.match_many("u1", [_topic("t1"), _topic("t2")])

    assert cache.locks_issued["t1"].release_attempts == 1, (
        "release 시도는 있어야 한다(실패하더라도)"
    )
    assert cache.locks_issued["t2"].released, "t1 release 실패가 t2 release 를 막으면 안 된다"
