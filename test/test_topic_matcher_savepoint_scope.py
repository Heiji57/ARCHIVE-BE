"""TopicMatcher._resolve — SAVEPOINT 가 벡터 검색 + find_by_ids 전체를 덮는지.

GitHub #4: `chunk_repo.py` 의 `_fetch_in_savepoint` 는 벡터 검색 두 개만 감쌌다.
`TopicMatcher._resolve` 가 그 직후 같은 세션에서 여는 `entry_repo.find_by_ids` /
`todo_repo.find_by_ids` 는 SAVEPOINT 밖에 있어서, 거기서 실패하면
`GetTopicsUseCase` 가 예외를 삼킨 뒤 이어지는 조회(예: digest watermark)가
InFailedSQLTransaction 으로 다시 죽는다 — SAVEPOINT 를 넣은 이유였던 바로 그 500.

수정: `_resolve` 전체(벡터 검색 2회 + find_by_ids 2회)를 `ITopicMatchTransaction.nested()`
하나로 감싼다. 이 테스트는 Postgres 의 "SAVEPOINT 밖에서 깨지면 트랜잭션 전체 폐기"
의미를 흉내 내는 페이크 세션 위에서, find_by_ids 실패가 세션 전체를 죽이지 않는지
확인한다 — `test_topic_vector_search.py` 의 `_FakeSession` 과 같은 모델이지만, 벡터
검색만이 아니라 `_resolve` 가 여는 모든 문장을 추적하도록 일반화했다.
"""
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from app.shared.infrastructure.config.topic import TopicConfig
from app.topic.application.services.topic_matcher import TopicMatcher
from app.topic.domain.models.topic import SimilarChunk, SimilarTodo, Topic

_NOW = datetime.now(UTC)


class _StatementError(RuntimeError):
    """문장 하나가 DB 에서 거절된 상황(제약 위반, 타임아웃 등) 대역."""


class _TransactionAbortedError(RuntimeError):
    """asyncpg 의 InFailedSQLTransactionError 대역 — SAVEPOINT 밖에서 깨진 뒤 세션이
    폐기된 상태로 다음 문장을 받으면 이게 난다."""


class _Savepoint:
    def __init__(self, session: "_FakeSession") -> None:
        self._session = session

    async def __aenter__(self) -> "_Savepoint":
        self._session.depth += 1
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        # 예외로 빠져나오면 ROLLBACK TO SAVEPOINT — 바깥은 살아남는다. swallow 하지 않는다.
        self._session.depth -= 1
        return False


@dataclass
class _FakeSession:
    """실제 `SqlAlchemyTopicMatchTransaction` 이 감싸는 세션의 실패 의미론을 흉내낸다.

    `run(op)` 을 거치는 모든 가짜 리포지터리 호출이 이 세션을 공유한다 — 실제 DI 에서
    entry_repo/todo_repo/chunk_repo/todo_emb_repo 가 요청 스코프의 같은 `AsyncSession`
    을 주입받는 것과 동일한 구도.
    """

    depth: int = 0
    aborted: bool = False
    fail_on: set[str] = field(default_factory=set)
    calls: list[str] = field(default_factory=list)

    def begin_nested(self) -> _Savepoint:
        return _Savepoint(self)

    async def run(self, op: str):
        if self.aborted:
            raise _TransactionAbortedError(f"current transaction is aborted ({op})")
        self.calls.append(op)
        if op in self.fail_on:
            if self.depth == 0:
                self.aborted = True  # SAVEPOINT 밖에서 깨지면 세션 전체가 죽는다
            raise _StatementError(f"{op} failed")


class _FakeTransaction:
    """ITopicMatchTransaction 대역 — 실제 SqlAlchemyTopicMatchTransaction 과 동일하게
    공유 세션의 begin_nested() 를 그대로 위임한다."""

    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def nested(self):
        return self._session.begin_nested()


class _ChunkRepo:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def search_similar(self, **kwargs) -> list[SimilarChunk]:
        await self._session.run("chunk.search_similar")
        return [
            SimilarChunk(id="c1", entry_id="e1", chunk_index=0, text="t", date_key="2026-09-01")
        ]


class _TodoEmbRepo:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def search_similar(self, **kwargs) -> list[SimilarTodo]:
        await self._session.run("todo_emb.search_similar")
        return []


class _EntryRepo:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def find_by_ids(self, user_id, ids):
        await self._session.run("entry.find_by_ids")
        return []


class _TodoRepo:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def find_by_ids(self, user_id, ids):
        await self._session.run("todo.find_by_ids")
        return []


class _StubEmbeddingService:
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 4 for _ in texts]


class _NoOpCache:
    async def get(self, topic_id, name, description):
        return None

    async def set(self, topic_id, name, description, payload):
        pass


def _matcher(session: _FakeSession) -> TopicMatcher:
    return TopicMatcher(
        embedding_service=_StubEmbeddingService(),
        chunk_repo=_ChunkRepo(session),
        todo_emb_repo=_TodoEmbRepo(session),
        entry_repo=_EntryRepo(session),
        todo_repo=_TodoRepo(session),
        cache=_NoOpCache(),
        config=TopicConfig(),
        transaction=_FakeTransaction(session),
    )


_TOPIC = Topic(id="tpc_1", user_id="u1", name="배포", description="", created_at=_NOW)


async def test_find_by_ids_failure_does_not_abort_the_outer_session() -> None:
    """이게 #4 의 핵심 — find_by_ids 가 SAVEPOINT 밖에 있었을 때는 실패했다."""
    session = _FakeSession(fail_on={"entry.find_by_ids"})
    matcher = _matcher(session)

    with pytest.raises(_StatementError):
        await matcher.match("u1", _TOPIC)

    assert not session.aborted, "find_by_ids 실패가 세션 전체를 죽였다 — SAVEPOINT 밖에 있다는 뜻"
    # 세션이 살아 있다면 뒤이은 문장(예: GetTopicsUseCase 의 digest watermark 조회)이 통과해야 한다.
    await session.run("digest.find_by_topic")


async def test_vector_search_failure_still_does_not_abort_the_outer_session() -> None:
    """기존에 지켜지던 것도 함께 — 회귀 방지."""
    session = _FakeSession(fail_on={"chunk.search_similar"})
    matcher = _matcher(session)

    with pytest.raises(_StatementError):
        await matcher.match("u1", _TOPIC)

    assert not session.aborted
    await session.run("digest.find_by_topic")


async def test_successful_resolve_makes_all_four_calls_inside_one_savepoint() -> None:
    session = _FakeSession()
    matcher = _matcher(session)

    await matcher.match("u1", _TOPIC)

    assert session.calls == [
        "chunk.search_similar",
        "todo_emb.search_similar",
        "entry.find_by_ids",
        "todo.find_by_ids",
    ]
    assert session.depth == 0, "SAVEPOINT 가 닫히지 않았다"
