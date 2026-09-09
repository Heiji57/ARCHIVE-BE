"""주제 통계/소스 + 회고 기본 제목 + todos stats range=all 검증.

이 저장소엔 pytest 가 설치/선언돼 있지 않아 다른 테스트와 동일하게 직접 실행 가능한
스크립트로 작성한다.

실행:
    PYTHONPATH=src python test/test_topic_stats_and_entry_title.py
"""
import asyncio
import sys
from datetime import date, datetime, timezone

from app.retrospective.domain.constants.entry_title_defaults import (
    default_entry_title,
    resolve_entry_title,
)
from app.retrospective.domain.models.value_objects import RetroType
from app.todo.application.use_cases.get_todo_stats import _range_bounds
from app.todo.domain.utils.recurrence import generate_slots_from
from app.topic.application.dtos.matching import MatchedEntry, MatchedTodo, TopicMatch
from app.topic.application.dtos.queries import GetTopicSourcesQuery, GetTopicStatsQuery
from app.topic.application.use_cases.get_topic_sources import GetTopicSourcesUseCase
from app.topic.application.use_cases.get_topic_stats import GetTopicStatsUseCase
from app.topic.domain.models.topic import Topic, TopicDigest
from app.topic.domain.models.value_objects import DigestStatus

_NOW = datetime.now(timezone.utc)
_TOPIC = Topic(id="tpc_1", user_id="u1", name="배포", description="배포 자동화", created_at=_NOW)

_MATCH = TopicMatch(
    entries=[
        MatchedEntry(id="e1", title="A", date_key="2026-09-05", retro_type="daily"),
        MatchedEntry(id="e2", title="B", date_key="2026-08-30", retro_type="daily"),
        MatchedEntry(id="e3", title="C", date_key="2026-09-02", retro_type="weekly"),
    ],
    todos=[
        MatchedTodo(id="t1", title="T1", date_key="2026-09-06", status="done", tags=["배포", "CI"]),
        MatchedTodo(id="t2", title="T2", date_key="2026-09-01", status="in-progress", tags=["배포"]),
    ],
)


class _TopicRepo:
    async def find_by_id(self, topic_id, user_id):
        return _TOPIC if topic_id == _TOPIC.id else None


class _DigestRepo:
    def __init__(self, watermark: str | None) -> None:
        self._watermark = watermark

    async def find_by_topic(self, topic_id, user_id):
        if self._watermark is None:
            return None
        return TopicDigest(
            id="d1",
            topic_id=topic_id,
            user_id=user_id,
            status=DigestStatus.COMPLETED,
            content="x",
            watermark_date_key=self._watermark,
            created_at=_NOW,
        )


class _Matcher:
    async def match(self, user_id, topic):
        return _MATCH


def _check(label: str, actual, expected) -> None:
    if actual != expected:
        print(f"FAIL {label}: expected {expected!r}, got {actual!r}")
        sys.exit(1)
    print(f"ok   {label}")


async def test_stats() -> None:
    stats = await GetTopicStatsUseCase(_TopicRepo(), _DigestRepo("2026-09-01"), _Matcher()).execute(
        GetTopicStatsQuery(user_id="u1", topic_id="tpc_1")
    )
    _check("entry_counts by retro_type", (stats.entry_counts.daily, stats.entry_counts.weekly), (2, 1))
    _check("entry_counts.total", stats.entry_counts.total, 3)
    # 매칭 규칙상 not-start 는 애초에 들어오지 않는다. completed 는 done 만 센다.
    _check("todo_counts", (stats.todo_counts.total, stats.todo_counts.completed), (2, 1))
    # 태그는 count 내림차순, 동률이면 tag 오름차순
    _check("tag_counts", [(t.tag, t.count) for t in stats.tag_counts], [("배포", 2), ("CI", 1)])
    _check("tag_count_total", stats.tag_count_total, 2)
    # 기간은 회고+할일을 합친 min/max
    _check("period", (stats.period_start_date_key, stats.period_end_date_key), ("2026-08-30", "2026-09-06"))
    # 워터마크 "초과"만 미반영 — 09-05, 09-02 (08-30 은 이전)
    _check("unreflected with watermark", stats.unreflected_entry_count, 2)


async def test_unreflected_excludes_watermark_day() -> None:
    """정리한 당일 회고는 미반영이 아니다 — 방금 정리했는데 '미반영 1개'가 뜨면 안 된다."""
    match = TopicMatch(
        entries=[
            MatchedEntry(id="e1", title="정리 당일", date_key="2026-09-01", retro_type="daily"),
            MatchedEntry(id="e2", title="이후", date_key="2026-09-02", retro_type="daily"),
        ],
        todos=[],
    )

    class _M:
        async def match(self, user_id, topic):
            return match

    stats = await GetTopicStatsUseCase(_TopicRepo(), _DigestRepo("2026-09-01"), _M()).execute(
        GetTopicStatsQuery(user_id="u1", topic_id="tpc_1")
    )
    _check("watermark-day entry not counted as unreflected", stats.unreflected_entry_count, 1)


async def test_stats_without_digest() -> None:
    stats = await GetTopicStatsUseCase(_TopicRepo(), _DigestRepo(None), _Matcher()).execute(
        GetTopicStatsQuery(user_id="u1", topic_id="tpc_1")
    )
    # digest 가 없으면 매칭되는 전체 회고 수가 미반영 수다.
    _check("unreflected without digest", stats.unreflected_entry_count, 3)


async def test_sources_pagination() -> None:
    use_case = GetTopicSourcesUseCase(_TopicRepo(), _DigestRepo("2026-09-01"), _Matcher())
    page1 = await use_case.execute(
        GetTopicSourcesQuery(user_id="u1", topic_id="tpc_1", page=1, size=3)
    )
    page2 = await use_case.execute(
        GetTopicSourcesQuery(user_id="u1", topic_id="tpc_1", page=2, size=3)
    )
    _check("sources total", page1.total, 5)
    _check("sources watermark", page1.digest_watermark_date_key, "2026-09-01")
    _check(
        "sources sorted desc by date_key",
        [i.date_key for i in page1.items] + [i.date_key for i in page2.items],
        ["2026-09-06", "2026-09-05", "2026-09-02", "2026-09-01", "2026-08-30"],
    )
    ids = [i.id for i in page1.items] + [i.id for i in page2.items]
    _check("no duplicate/missing across pages", sorted(ids), ["e1", "e2", "e3", "t1", "t2"])
    _check("entry carries retro_type", next(i.retro_type for i in page1.items if i.id == "e1"), "daily")
    _check("todo has no retro_type", next(i.retro_type for i in page1.items if i.id == "t1"), None)


async def test_topics_list_degrades_when_embedding_fails() -> None:
    """카운트는 부가 정보 — 임베딩 API 가 죽어도 목록은 200 으로 내려와야 한다."""
    from app.topic.application.dtos.queries import GetTopicsQuery
    from app.topic.application.use_cases.get_topics import GetTopicsUseCase

    class _ListRepo:
        async def find_all_by_user(self, user_id):
            return [_TOPIC]

    class _BrokenMatcher:
        async def match_many(self, user_id, topics):
            raise RuntimeError("embedding quota exhausted")

    summaries = await GetTopicsUseCase(_ListRepo(), _DigestRepo("2026-09-01"), _BrokenMatcher()).execute(
        GetTopicsQuery(user_id="u1")
    )
    _check("list still returned", len(summaries), 1)
    _check("counts nulled on failure", (summaries[0].entry_count, summaries[0].todo_count), (None, None))
    # 워터마크는 DB 조회라 임베딩 장애와 무관하게 유지된다.
    _check("watermark preserved", summaries[0].digest_watermark_date_key, "2026-09-01")


async def test_topics_list_counts() -> None:
    from app.topic.application.dtos.queries import GetTopicsQuery
    from app.topic.application.use_cases.get_topics import GetTopicsUseCase
    from app.topic.presentation.router import _to_topic_summary_response

    class _ListRepo:
        async def find_all_by_user(self, user_id):
            return [_TOPIC]

    class _ListMatcher:
        async def match_many(self, user_id, topics):
            return {t.id: _MATCH for t in topics}

    summaries = await GetTopicsUseCase(_ListRepo(), _DigestRepo("2026-09-01"), _ListMatcher()).execute(
        GetTopicsQuery(user_id="u1")
    )
    _check("counts match stats totals", (summaries[0].entry_count, summaries[0].todo_count), (3, 2))
    # 라우터 매핑까지 통과하는지 (Pydantic 응답 조립)
    response = _to_topic_summary_response(summaries[0])
    _check(
        "router response carries counts",
        (response.entry_count, response.todo_count, response.digest_watermark_date_key),
        (3, 2, "2026-09-01"),
    )


def test_entry_titles() -> None:
    _check("ko daily", default_entry_title("2026-09-03", RetroType.DAILY, "ko"), "2026-09-03 일일 회고")
    _check(
        "en yearly",
        default_entry_title("2026-09-03", RetroType.YEARLY, "en"),
        "2026-09-03 Annual Retrospective",
    )
    _check("locale region stripped", default_entry_title("2026-09-03", RetroType.DAILY, "ko-KR"), "2026-09-03 일일 회고")
    # 매핑 없는 locale·None 은 en 폴백
    _check(
        "unknown locale falls back to en",
        default_entry_title("2026-09-03", RetroType.DAILY, "pt-BR"),
        "2026-09-03 Daily Retrospective",
    )
    _check(
        "none locale falls back to en",
        default_entry_title("2026-09-03", RetroType.DAILY, None),
        "2026-09-03 Daily Retrospective",
    )
    _check("blank title filled", resolve_entry_title("   ", "2026-09-03", RetroType.WEEKLY, "ko"), "2026-09-03 주간 회고")
    _check("given title kept", resolve_entry_title("내 제목", "2026-09-03", RetroType.WEEKLY, "ko"), "내 제목")


def test_range_all_is_bounded() -> None:
    today = date(2026, 9, 8)
    _check("all range floor/ceiling", _range_bounds(today, "all"), (date(2000, 1, 1), today))
    _check("today unchanged", _range_bounds(today, "today"), (today, today))
    _check("month unchanged", _range_bounds(today, "month"), (date(2026, 9, 1), date(2026, 9, 30)))

    # 종료일 없는 매일 반복이 range=all 에서 유계로 끝나는지 — 상한이 date.max 면
    # 서기 9999년까지 수백만 슬롯이 생겨 요청이 사실상 멈춘다.
    class _Rule:
        unit = "day"
        interval = 1
        until = None

    start, end = _range_bounds(today, "all")
    slots = generate_slots_from(_Rule(), "2026-01-01", start.isoformat(), end.isoformat())
    _check("daily recurrence bounded by today", (len(slots) < 10_000, slots[-1]), (True, "2026-09-08"))


async def main() -> None:
    await test_stats()
    await test_unreflected_excludes_watermark_day()
    await test_stats_without_digest()
    await test_sources_pagination()
    await test_topics_list_counts()
    await test_topics_list_degrades_when_embedding_fails()
    test_entry_titles()
    test_range_all_is_bounded()
    print("\nAll topic stats / entry title / range=all tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
