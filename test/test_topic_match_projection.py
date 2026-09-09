"""주제 매칭 경로가 읽지도 않을 큰 컬럼을 실어오지 않는지.

GitHub #7: `TopicMatcher._resolve` 가 회고를 `select(JournalEntryModel)` 로 통째로
가져오면서 본문 `content` 와 전문검색 벡터 `content_tsv` 까지 실어왔다. 할일도
반복 규칙·캘린더 push 상태를 포함한 스물몇 개 컬럼을 통째로 가져왔다. 그런데 매칭이
쓰는 건 회고 4필드·할일 5필드뿐이다. 벡터 검색도 마찬가지로 청크 본문(`text`)을
실어오는데 매칭은 `entry_id` 만 읽는다(`text` 를 읽는 건 digest 워커뿐).

여기서는 실제로 만들어지는 SQL 을 컴파일해 "안 읽는 컬럼이 SELECT 목록에 없다"를
잠근다. 되돌리면(전체 컬럼 SELECT 로) 곧바로 실패한다.
"""
import re

from sqlalchemy.dialects import postgresql

from app.retrospective.infrastructure.persistence.repositories.journal_entry_repo import (
    JournalEntryRepository,
)
from app.todo.infrastructure.persistence.repositories.todo_repo import TodoRepository
from app.topic.infrastructure.persistence.repositories.chunk_repo import (
    EntryChunkRepository,
    TodoEmbeddingRepository,
)

_EMBEDDING = [0.01] * 768


class _EmptyResult:
    def all(self) -> list:
        return []


class _Savepoint:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _CapturingSession:
    """실행은 하지 않고 statement 만 붙잡아 두는 세션."""

    def __init__(self) -> None:
        self.statements: list = []

    def begin_nested(self) -> _Savepoint:
        return _Savepoint()

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _EmptyResult()


def _sql(stmt) -> str:
    compiled = stmt.compile(dialect=postgresql.dialect(paramstyle="numeric_dollar"))
    return re.sub(r"\s+", " ", str(compiled))


def _select_list(sql: str) -> str:
    """가장 바깥 SELECT ... FROM 사이 — 실제로 실어오는 컬럼 목록."""
    return sql.split(" FROM ", 1)[0]


async def _capture_one(coro_factory) -> str:
    session = _CapturingSession()
    await coro_factory(session)
    assert len(session.statements) == 1
    return _sql(session.statements[0])


async def test_entry_lookup_does_not_load_content_or_tsvector() -> None:
    """회고 본문·tsvector 는 행마다 가장 큰 컬럼인데 매칭은 읽지 않는다."""
    sql = await _capture_one(
        lambda s: JournalEntryRepository(s).find_meta_by_ids("u1", ["e1", "e2"])
    )
    select_list = _select_list(sql)

    assert "content" not in select_list, f"본문/tsvector 를 실어오고 있다: {select_list}"
    for column in ("id", "date_key", "title", "retro_type"):
        assert f"journal_entries.{column}" in select_list, f"{column} 이 빠졌다"


async def test_todo_lookup_loads_only_the_five_fields_matching_uses() -> None:
    """반복 규칙·캘린더 push 상태 등은 매칭이 읽지 않는다."""
    sql = await _capture_one(lambda s: TodoRepository(s).find_meta_by_ids("u1", ["t1"]))
    select_list = _select_list(sql)

    for unused in (
        "description",
        "recurrence_rule",
        "google_event_id",
        "calendar_push_status",
        "start_time",
        "completed_at",
    ):
        assert unused not in select_list, f"{unused} 를 실어오고 있다: {select_list}"
    for column in ("id", "title", "date_key", "status", "tags"):
        assert f"todos.{column}" in select_list, f"{column} 이 빠졌다"


async def test_entry_id_search_does_not_load_chunk_text() -> None:
    sql = await _capture_one(
        lambda s: EntryChunkRepository(s).search_similar_entry_ids(
            user_id="u1",
            query_embedding=_EMBEDDING,
            since_date_key=None,
            threshold=0.75,
            limit=1000,
        )
    )
    assert ".text" not in sql, f"청크 본문을 실어오고 있다: {sql}"
    assert "entry_id" in _select_list(sql)


async def test_entry_id_search_limits_by_entry_not_by_chunk() -> None:
    """상한 단위가 **회고**여야 한다 — 청크로 자르면 천장이 글 길이에 따라 달라진다 (#10).

    청크는 단락 길이에 따라 회고당 2~4개로 갈리는 내부 단위인데, 사용자에게 보이는
    건 "회고 N건" 이다. 청크로 자르면 (a) 글을 길게 쓰는 사용자일수록 카운트 천장이
    낮아지고, (b) 청크가 많은 긴 회고 하나가 슬롯을 여러 개 차지해 다른 회고를
    밀어낸다. GROUP BY entry_id + ORDER BY min(거리) 로 회고마다 정확히 한 자리만
    쓰게 한다.
    """
    sql = await _capture_one(
        lambda s: EntryChunkRepository(s).search_similar_entry_ids(
            user_id="u1",
            query_embedding=_EMBEDDING,
            since_date_key=None,
            threshold=0.75,
            limit=1000,
        )
    )

    assert "GROUP BY topic_entry_chunks.entry_id" in sql, (
        f"회고 단위로 접지 않으면 상한이 청크 기준이 된다: {sql}"
    )
    # min() 이 감싸는 대상까지 확인한다 — min(chunk_index) 나 min(created_at) 으로
    # 순위를 매기는 구현도 "ORDER BY min(" 만 보면 통과해버린다.
    assert "ORDER BY min(topic_entry_chunks.embedding <=>" in sql, (
        f"회고 순위는 그 회고의 가장 가까운 청크의 코사인 거리여야 한다: {sql}"
    )
    # LIMIT 이 GROUP BY 뒤에 있어야 "회고 N개" 가 된다. 서브쿼리에서 청크를 먼저
    # 자르는 옛 방식이면 이 순서가 뒤집힌다.
    assert sql.index("GROUP BY") < sql.index("LIMIT")
    assert "FROM (SELECT" not in sql, f"청크를 먼저 자르는 서브쿼리가 남아 있다: {sql}"


async def test_todo_id_search_does_not_load_todo_text() -> None:
    sql = await _capture_one(
        lambda s: TodoEmbeddingRepository(s).search_similar_todo_ids(
            user_id="u1",
            query_embedding=_EMBEDDING,
            since_date_key=None,
            threshold=0.75,
            limit=1000,
        )
    )
    assert ".text" not in sql, f"할일 임베딩 텍스트를 실어오고 있다: {sql}"
    assert "todo_id" in _select_list(sql)
    # 상태 필터(not-start 제외)는 그대로 유지돼야 한다.
    assert "status IN" in sql


async def test_digest_path_still_loads_text() -> None:
    """워커는 프롬프트 조립에 본문이 필요하다 — 좁히면 안 되는 쪽."""
    session = _CapturingSession()
    await EntryChunkRepository(session).search_similar(
        user_id="u1",
        query_embedding=_EMBEDDING,
        since_date_key=None,
        threshold=0.75,
        limit=200,
    )
    assert "topic_entry_chunks.text" in _select_list(_sql(session.statements[0]))
