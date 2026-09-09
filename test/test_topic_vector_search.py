"""주제 벡터 검색 — SQL 파라미터 바인딩 + 트랜잭션 격리 회귀 테스트.

배경: `GET /topics` 가 500 을 냈다. 방아쇠는 raw ``text()`` 안의 ``:emb::vector`` 였다.
SQLAlchemy 의 바인드 파서는 이름 뒤에 콜론이 붙으면 Postgres 캐스트로 보고 바인딩을
건너뛰므로 ``:emb`` 가 문자 그대로 DB 에 넘어가 구문 오류가 났다.

하지만 500 을 만든 것은 구문 오류 자체가 아니라 그 뒤의 연쇄다. `GetTopicsUseCase` 가
매칭 실패를 삼키고 카운트만 비우도록 설계돼 있는데, Postgres 는 문장 하나가 깨지면
트랜잭션 전체를 폐기하므로 예외를 삼킨 뒤 같은 세션에서 이어지는 조회가
InFailedSQLTransaction 으로 죽었다. 즉 degradation 경로가 DB 오류에는 작동하지 않았다.

그래서 두 층을 다 잠근다 — 쿼리가 올바르게 바인딩되는지, 그리고 쿼리가 깨져도 세션이
살아남는지.
"""
import re
from datetime import UTC, datetime

import pytest
from sqlalchemy.dialects import postgresql

from app.topic.application.dtos.queries import GetTopicsQuery
from app.topic.application.use_cases.get_topics import GetTopicsUseCase
from app.topic.domain.models.topic import Topic, TopicDigest
from app.topic.domain.models.value_objects import DigestStatus
from app.topic.infrastructure.persistence.repositories.chunk_repo import (
    EntryChunkRepository,
    TodoEmbeddingRepository,
)

_NOW = datetime.now(UTC)
_TOPIC = Topic(id="tpc_1", user_id="u1", name="배포", description="배포 자동화", created_at=_NOW)
_EMBEDDING = [0.01 * i for i in range(768)]

# SQLAlchemy 가 치환하지 못하고 남긴 ``:name`` 을 찾는 패턴. 이게 잡히면 그 문장은
# 그대로 Postgres 로 가서 구문 오류가 난다 — 원래 버그의 형태.
_UNBOUND_BIND = re.compile(r"(?<![:\w$]):[\w$]+")


class _TransactionAbortedError(RuntimeError):
    """asyncpg 의 InFailedSQLTransactionError 대역."""


class _StatementError(RuntimeError):
    """문장 하나가 DB 에서 거절된 상황 (구문 오류, 타임아웃 등) 대역."""


class _Savepoint:
    def __init__(self, session: "_FakeSession") -> None:
        self._session = session

    async def __aenter__(self) -> "_Savepoint":
        self._session.depth += 1
        self._session.max_depth = max(self._session.max_depth, self._session.depth)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        # 예외로 빠져나오면 ROLLBACK TO SAVEPOINT — 바깥 트랜잭션은 살아남는다.
        self._session.depth -= 1
        return False


class _FakeSession:
    """Postgres 의 "문장 하나가 깨지면 트랜잭션 전체 폐기" 의미를 흉내 내는 세션.

    SAVEPOINT 밖에서 문장이 깨지면 이후 모든 문장이 죽고, 안에서 깨지면 회복된다.
    이 규칙이 있어야 원래 버그가 테스트에서 재현된다 — 순수 예외로는 재현되지 않는다.
    """

    def __init__(self, *, fail_search: bool = False) -> None:
        # 깨지는 것은 "문장 하나" 다 — 벡터 검색만 거절되고 뒤따르는 조회는 멀쩡해야
        # 원래 상황이 재현된다. 그래서 첫 문장만 실패시킨다.
        self._remaining_failures = 1 if fail_search else 0
        self.aborted = False
        self.depth = 0
        self.max_depth = 0
        self.statements: list = []

    def begin_nested(self) -> _Savepoint:
        return _Savepoint(self)

    async def execute(self, stmt):
        if self.aborted:
            raise _TransactionAbortedError("current transaction is aborted")
        if self._remaining_failures:
            self._remaining_failures -= 1
            if self.depth == 0:
                self.aborted = True  # SAVEPOINT 가 없으면 트랜잭션 전체가 폐기된다
            raise _StatementError("syntax error at or near \":\"")
        self.statements.append(stmt)
        return _EmptyResult()


class _EmptyResult:
    def all(self) -> list:
        return []


def _compile(stmt) -> tuple[str, dict]:
    compiled = stmt.compile(dialect=postgresql.dialect(paramstyle="numeric_dollar"))
    return str(compiled), dict(compiled.params)


async def _run_all_searches(session: _FakeSession) -> None:
    for repo in (EntryChunkRepository(session), TodoEmbeddingRepository(session)):
        for since_date_key in (None, "2026-01-01"):
            await repo.search_similar(
                user_id="u1",
                query_embedding=_EMBEDDING,
                since_date_key=since_date_key,
                threshold=0.75,
                limit=200,
            )


async def test_every_vector_search_binds_its_embedding() -> None:
    """네 갈래(회고/할일 × since 유무) 모두 임베딩이 실제 파라미터로 나가야 한다."""
    session = _FakeSession()
    await _run_all_searches(session)
    assert len(session.statements) == 4

    for stmt in session.statements:
        sql, params = _compile(stmt)
        assert _UNBOUND_BIND.findall(sql) == [], f"치환되지 않은 바인드가 남았다: {sql}"
        assert "<=>" in sql, "코사인 거리 연산자가 사라지면 HNSW 인덱스를 못 탄다"
        assert any(
            isinstance(v, list) and len(v) == len(_EMBEDDING) for v in params.values()
        ), "임베딩이 파라미터로 전달되지 않았다"


async def test_vector_search_does_not_fetch_embeddings() -> None:
    """embedding 컬럼은 아무도 읽지 않는다 — SELECT 목록에 실리면 행마다 768 float 낭비."""
    session = _FakeSession()
    await _run_all_searches(session)

    for stmt in session.statements:
        sql, _ = _compile(stmt)
        select_list = sql.split("FROM")[0]
        assert ".embedding" not in select_list, f"embedding 을 조회하고 있다: {select_list}"
        # 다만 WHERE/ORDER BY 에서는 여전히 써야 한다.
        assert ".embedding" in sql.split("FROM", 1)[1]


async def test_vector_search_runs_inside_a_savepoint() -> None:
    session = _FakeSession()
    await _run_all_searches(session)
    assert session.max_depth == 1, "검색이 SAVEPOINT 안에서 돌지 않았다"
    assert session.depth == 0, "SAVEPOINT 가 닫히지 않았다"


async def test_failed_search_leaves_session_usable() -> None:
    """검색이 깨져도 바깥 트랜잭션은 살아 있어야 한다 — 500 의 실제 원인."""
    session = _FakeSession(fail_search=True)
    repo = EntryChunkRepository(session)

    with pytest.raises(_StatementError):
        await repo.search_similar(
            user_id="u1",
            query_embedding=_EMBEDDING,
            since_date_key=None,
            threshold=0.75,
            limit=200,
        )

    assert not session.aborted, "SAVEPOINT 가 없어 트랜잭션 전체가 폐기됐다"
    await session.execute(None)  # 후속 조회가 살아야 한다


class _ListRepo:
    async def find_all_by_user(self, user_id: str) -> list[Topic]:
        return [_TOPIC]


class _SessionBackedDigestRepo:
    """워터마크 조회 — 목록 유스케이스가 매칭 뒤에 같은 세션으로 도는 조회를 대변한다."""

    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def find_by_topics(self, topic_ids: list[str], user_id: str) -> dict[str, TopicDigest]:
        await self._session.execute(None)
        return {
            tid: TopicDigest(
                id="dig_1",
                topic_id=tid,
                user_id=user_id,
                status=DigestStatus.COMPLETED,
                watermark_date_key="2026-09-01",
                created_at=_NOW,
            )
            for tid in topic_ids
        }


async def test_topics_list_degrades_when_db_search_fails() -> None:
    """DB 오류에서도 목록은 200 — 기존 degradation 테스트가 못 잡던 경로."""

    session = _FakeSession(fail_search=True)

    class _RepoBackedMatcher:
        async def match_many(self, user_id: str, topics: list[Topic]) -> dict:
            # 실제 매처와 같은 지점에서 깨진다 — 진짜 저장소를 태워야 의미가 있다.
            await EntryChunkRepository(session).search_similar(
                user_id=user_id,
                query_embedding=_EMBEDDING,
                since_date_key=None,
                threshold=0.75,
                limit=1000,
            )
            raise AssertionError("unreachable")

    summaries = await GetTopicsUseCase(
        _ListRepo(), _SessionBackedDigestRepo(session), _RepoBackedMatcher()
    ).execute(GetTopicsQuery(user_id="u1"))

    assert len(summaries) == 1
    assert (summaries[0].entry_count, summaries[0].todo_count) == (None, None)
    # 워터마크는 매칭 실패와 무관한 별도 조회 — 세션이 살아 있어야만 채워진다.
    assert summaries[0].digest_watermark_date_key == "2026-09-01"
