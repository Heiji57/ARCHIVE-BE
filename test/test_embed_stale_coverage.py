"""모든 회고가 주제 집계에 잡히는지 — 청킹 폴백 + 누락 자가 복구.

GitHub #8: `_split_chunks` 가 `topic_chunk_min_chars`(20자) 미만 단락을 버리는데,
모든 단락이 그 미만이면 청크가 0개가 되어 임베딩이 아예 생성되지 않았다. 임베딩이
없으면 벡터 검색에 절대 걸리지 않으므로 그 회고는 `GET /topics` 카운트·`/stats`·
`/sources`·digest 어디에도 나타나지 않는다. 개발 DB 기준 35건 중 27건이 이 상태였다.

정책: **본문이 있는 회고는 반드시 청크를 최소 하나 갖는다.**

두 번째 구멍: 큐는 회고/할일 라우터에서만 채워져서, 코드를 고쳐도 이미 저장된
회고는 재시도 경로가 없었다. `enqueue_entries_missing_chunks` 가 그 간극을 메운다.
"""
import re

from sqlalchemy.dialects import postgresql

from app.topic.infrastructure.persistence.repositories.chunk_repo import (
    EmbeddingQueueRepository,
)
from app.worker.tasks.embed_stale import _split_chunks

_MAX = 500
_MIN = 20


def test_short_entry_still_produces_a_chunk() -> None:
    """모든 단락이 20자 미만 — 예전에는 청크 0개라 영구 누락됐다."""
    content = "오늘은 쉬었다."

    chunks = _split_chunks(content, _MAX, _MIN)

    assert chunks, "짧은 회고가 청크를 하나도 못 만들면 주제 집계에서 사라진다"
    assert "오늘은 쉬었다." in " ".join(chunks)


def test_short_multi_paragraph_entry_becomes_one_semantic_unit() -> None:
    """짧은 단락 여럿은 통째로 하나로 묶는다 — 조각마다 임베딩하면 잡음이 된다."""
    content = "제목\n\n오늘은 쉬었다.\n\n끝"

    chunks = _split_chunks(content, _MAX, _MIN)

    assert len(chunks) == 1, f"조각마다 임베딩하고 있다: {chunks}"
    for fragment in ("제목", "오늘은 쉬었다.", "끝"):
        assert fragment in chunks[0]


def test_empty_or_whitespace_content_yields_nothing() -> None:
    """임베딩할 내용이 없으면 청크도 없다 — 자가 복구가 매 주기 되돌리지 않도록."""
    assert _split_chunks("", _MAX, _MIN) == []
    assert _split_chunks("   \n\n  \t ", _MAX, _MIN) == []


def test_long_entry_still_drops_filler_paragraphs() -> None:
    """폴백은 '결과가 빌 때'만 — 긴 회고 안의 짧은 잡음 단락은 여전히 걸러낸다."""
    body = "가" * 100
    content = f"제목\n\n{body}\n\n끝"

    chunks = _split_chunks(content, _MAX, _MIN)

    assert chunks == [body], f"짧은 단락이 섞여 들어왔다: {chunks}"


def test_fallback_respects_the_length_cap() -> None:
    """짧은 단락이 아주 많아도 청크 하나가 상한을 넘지 않아야 한다."""
    content = "\n\n".join(["짧은 줄"] * 400)

    chunks = _split_chunks(content, _MAX, _MIN)

    assert chunks
    assert all(len(c) <= _MAX for c in chunks), [len(c) for c in chunks]


def test_oversized_sentence_is_still_capped() -> None:
    """". " 로 안 쪼개지는 긴 단락(마침표 뒤 줄바꿈만 있는 한국어 글)도 상한을 지킨다.

    예전에는 이런 단락이 통째로 청크가 되어 상한을 넘겼다. 임베딩 API 가 거절하면
    큐 항목이 지워지지 않아 5분마다 영원히 재시도된다 — 그 회고는 결국 집계에서
    빠지고 API 호출만 계속 태운다.
    """
    content = "나" * (_MAX * 3 + 7)

    chunks = _split_chunks(content, _MAX, _MIN)

    assert chunks
    assert all(len(c) <= _MAX for c in chunks), [len(c) for c in chunks]
    # min_chars 미만 끝자락 하나만 버려질 수 있다 — 그 외에는 본문을 덮어야 한다.
    assert len("".join(chunks)) >= len(content) - _MIN


# ── 자가 복구 조회 ────────────────────────────────────────────────────────────


class _EmptyResult:
    def all(self) -> list:
        return []


class _CapturingSession:
    def __init__(self) -> None:
        self.statements: list = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _EmptyResult()

    async def flush(self) -> None:
        pass


async def test_requeue_query_skips_entries_that_already_have_chunks() -> None:
    session = _CapturingSession()

    await EmbeddingQueueRepository(session).enqueue_entries_missing_chunks(100)

    sql = re.sub(
        r"\s+",
        " ",
        str(session.statements[0].compile(dialect=postgresql.dialect())),
    )
    assert "NOT (EXISTS" in sql, f"이미 임베딩된 회고까지 다시 넣고 있다: {sql}"
    assert "topic_entry_chunks.entry_id = journal_entries.id" in sql


async def test_requeue_query_skips_blank_content() -> None:
    """공백뿐인 회고를 넣으면 청크가 안 생겨 매 주기 되돌아온다 — 무한 churn."""
    session = _CapturingSession()

    await EmbeddingQueueRepository(session).enqueue_entries_missing_chunks(100)

    sql = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "journal_entries.content ~" in sql, f"공백 본문을 걸러내지 않는다: {sql}"


async def test_requeue_writes_nothing_when_no_entries_are_missing() -> None:
    """되돌릴 게 없으면 INSERT 를 아예 발행하지 않는다."""
    session = _CapturingSession()

    count = await EmbeddingQueueRepository(session).enqueue_entries_missing_chunks(100)

    assert count == 0
    assert len(session.statements) == 1, "빈 결과인데 INSERT 까지 날렸다"


async def test_requeue_filter_excludes_every_character_python_treats_as_blank() -> None:
    """SQL 필터와 파이썬 청킹의 "공백" 정의가 어긋나면 무한 requeue 가 된다.

    Postgres 의 `[[:space:]]` 는 NBSP(U+00A0)·FIGURE SPACE(U+2007) 등을 공백으로
    치지 않는데 파이썬 `str.strip()` 은 제거한다. 그래서 `\\S` 로 필터하면 "DB 는
    내용이 있다고 보는데 청킹은 아무것도 못 만드는" 회고가 생겨, 매 주기 다시 잡히고
    다시 비는 churn 이 영원히 돈다.

    상수를 읽는 게 아니라 **실제로 DB 로 나가는 쿼리의 바인드 값**을 꺼내 검사한다 —
    상수만 보면 호출부가 다른 패턴을 쓰도록 바뀌어도 통과해버린다.
    """
    session = _CapturingSession()
    await EmbeddingQueueRepository(session).enqueue_entries_missing_chunks(100)

    compiled = session.statements[0].compile(dialect=postgresql.dialect())
    patterns = [
        v for v in compiled.params.values() if isinstance(v, str) and v.startswith("[^")
    ]
    assert len(patterns) == 1, f"공백 판정 패턴을 못 찾았다: {compiled.params}"
    pattern = patterns[0]

    body = pattern[len("[^") : -len("]")].replace("[:space:]", "")
    excluded: set[str] = set()
    for start_hex, end_hex in re.findall(
        r"\\u([0-9A-Fa-f]{4})(?:-\\u([0-9A-Fa-f]{4}))?", body
    ):
        start = int(start_hex, 16)
        end = int(end_hex, 16) if end_hex else start
        excluded.update(chr(c) for c in range(start, end + 1))

    # [:space:] 가 덮는 ASCII 공백은 패턴에 안 적혀 있어도 제외된다.
    ascii_space = set(" \t\n\r\v\f")
    python_blank = {chr(c) for c in range(0x110000) if chr(c).isspace()}

    missed = sorted(python_blank - excluded - ascii_space)
    assert not missed, (
        "SQL 필터가 놓치는 공백 문자 — 무한 requeue 대상: "
        + " ".join(f"U+{ord(c):04X}" for c in missed)
    )
    # 반대 방향 — 진짜 내용은 계속 걸러지지 않아야 한다.
    assert "가" not in excluded
    assert "a" not in excluded
