"""주제 목록 보강(한 줄 요약·기간·미반영 수·최근 한 일)과 정리 응답의 근거(`sources`)."""
from datetime import UTC, datetime
from types import SimpleNamespace

from app.retrospective.domain.models.value_objects import RetroType
from app.todo.domain.models.value_objects import TaskStatus
from app.topic.application.dtos.queries import GetTopicsQuery
from app.topic.application.use_cases.get_digest import GetDigestUseCase
from app.topic.application.use_cases.get_topics import GetTopicsUseCase
from app.topic.domain.models.structured_digest import (
    DigestItem,
    DigestTheme,
    StructuredDigest,
)
from app.topic.domain.models.topic import Topic, TopicDigest
from app.topic.domain.models.value_objects import DigestStatus

_NOW = datetime(2026, 11, 1, tzinfo=UTC)


def _topic(tid: str) -> Topic:
    return Topic(id=tid, user_id="usr_1", name=tid, created_at=_NOW)


def _structured() -> StructuredDigest:
    return StructuredDigest(
        summary="한 줄 요약",
        themes=[
            DigestTheme(
                key="t1",
                name="가",
                summary="",
                items=[
                    DigestItem("2026-10-21", "첫 일", "entry", "ent_a"),
                    DigestItem("2026-10-29", "할 일", "todo", "todo_x"),
                    DigestItem("2026-12-01", "미래", "todo", "todo_y"),
                ],
            ),
            DigestTheme(
                key="t2",
                name="나",
                summary="",
                items=[DigestItem("2026-10-25", "중간", "entry", "ent_gone")],
            ),
        ],
    )


def _digest(tid: str, **kw) -> TopicDigest:
    base = dict(
        id=f"dig_{tid}",
        topic_id=tid,
        user_id="usr_1",
        status=DigestStatus.COMPLETED,
        content="md",
        watermark_date_key="2026-10-30",
        structured=_structured(),
        created_at=_NOW,
    )
    base.update(kw)
    return TopicDigest(**base)


class _TopicRepo:
    def __init__(self, topics):
        self._topics = topics

    async def find_all_by_user(self, user_id):
        return self._topics

    async def find_by_id(self, topic_id, user_id):
        return next((t for t in self._topics if t.id == topic_id), None)


class _DigestRepo:
    def __init__(self, digests):
        self._digests = digests

    async def find_by_topics(self, topic_ids, user_id):
        return {d.topic_id: d for d in self._digests}

    async def find_by_topic(self, topic_id, user_id):
        return next((d for d in self._digests if d.topic_id == topic_id), None)


class _Matcher:
    def __init__(self, matches):
        self._matches = matches

    async def match_many(self, user_id, topics):
        return self._matches


def _match(entry_dates, todo_dates=()):
    return SimpleNamespace(
        entries=[SimpleNamespace(date_key=d) for d in entry_dates],
        todos=[SimpleNamespace(date_key=d) for d in todo_dates],
    )


async def test_list_fields_from_structured_digest():
    uc = GetTopicsUseCase(
        _TopicRepo([_topic("a"), _topic("b")]),  # type: ignore[arg-type]
        _DigestRepo([_digest("a")]),  # type: ignore[arg-type]
        _Matcher({"a": _match(["2026-10-21", "2026-10-30", "2026-11-02"]), "b": _match(["2026-09-01"], ["2026-09-03"])}),  # type: ignore[arg-type]  # noqa: E501
    )
    a, b = await uc.execute(
        GetTopicsQuery(user_id="usr_1", include_recent=True, today="2026-11-16")
    )

    assert a.digest_status == "completed"
    assert a.digest_summary == "한 줄 요약"
    # 정리가 있으면 정리 항목 날짜 기준
    assert (a.period_start_date_key, a.period_end_date_key) == ("2026-10-21", "2026-12-01")
    # 워터마크(10-30) 초과만 미반영
    assert a.unreflected_entry_count == 1
    # 오늘 이후(12-01) 제외, 날짜 내림차순, theme key 동반
    assert [(r.date_key, r.theme_key) for r in a.recent_items] == [
        ("2026-10-29", "t1"),
        ("2026-10-25", "t2"),
        ("2026-10-21", "t1"),
    ]

    # 정리가 없으면: 상태 none, 기간은 매칭 결과 기준, 미반영은 전체
    assert b.digest_status == "none" and b.digest_summary is None
    assert (b.period_start_date_key, b.period_end_date_key) == ("2026-09-01", "2026-09-03")
    assert b.unreflected_entry_count == 1
    assert b.recent_items == []


async def test_recent_items_only_when_requested():
    uc = GetTopicsUseCase(
        _TopicRepo([_topic("a")]),  # type: ignore[arg-type]
        _DigestRepo([_digest("a")]),  # type: ignore[arg-type]
        _Matcher({}),  # type: ignore[arg-type]
    )
    (a,) = await uc.execute(GetTopicsQuery(user_id="usr_1"))
    assert a.recent_items is None
    # 매칭 실패(빈 결과) 시 매칭 기반 값은 None, 정리 기반 값은 그대로
    assert a.entry_count is None and a.unreflected_entry_count is None
    assert a.digest_summary == "한 줄 요약"


class _EntryRepo:
    async def find_meta_by_ids(self, user_id, ids):
        # ent_gone 은 지워져 조회되지 않는다
        return [
            SimpleNamespace(
                id="ent_a", title="회고", date_key="2026-10-21", retro_type=RetroType.DAILY
            )
        ]


class _TodoRepo:
    async def find_meta_by_ids(self, user_id, ids):
        return [
            SimpleNamespace(id=i, title=f"할 일 {i}", date_key="2026-10-29", status=TaskStatus.DONE)
            for i in ids
        ]


async def test_digest_sources_are_current_and_skip_deleted():
    uc = GetDigestUseCase(
        _TopicRepo([]),  # type: ignore[arg-type]
        _DigestRepo([]),  # type: ignore[arg-type]
        _EntryRepo(),  # type: ignore[arg-type]
        _TodoRepo(),  # type: ignore[arg-type]
    )
    sources = await uc.resolve_sources(_digest("a"))
    assert set(sources) == {"ent_a", "todo_x", "todo_y"}
    assert sources["ent_a"].retro_type == "daily" and sources["ent_a"].status is None
    assert sources["todo_x"].status == "done" and sources["todo_x"].kind == "todo"


async def test_digest_sources_empty_without_structure():
    uc = GetDigestUseCase(None, None, _EntryRepo(), _TodoRepo())  # type: ignore[arg-type]
    assert await uc.resolve_sources(_digest("a", structured=None)) == {}
