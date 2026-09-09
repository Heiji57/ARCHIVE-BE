"""GetTopicsUseCase — digest watermark 조회가 topic 수만큼 왕복하는 N+1 인지.

GitHub #6: `for topic in topics: ... await self._digest_repo.find_by_topic(...)` 로
주제 수만큼 DB 왕복이 발생했다. `ITopicDigestRepository.find_by_topics` 배치 메서드로
한 번에 접는다.
"""
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.topic.application.dtos.queries import GetTopicsQuery
from app.topic.application.use_cases.get_topics import GetTopicsUseCase
from app.topic.domain.models.topic import Topic, TopicDigest
from app.topic.domain.models.value_objects import DigestStatus

_NOW = datetime.now(UTC)


def _topic(tid: str) -> Topic:
    return Topic(id=tid, user_id="u1", name=f"주제 {tid}", description="", created_at=_NOW)


class _ListRepo:
    def __init__(self, topics: list[Topic]) -> None:
        self._topics = topics

    async def find_all_by_user(self, user_id):
        return self._topics


class _EmptyMatcher:
    async def match_many(self, user_id, topics):
        return {}


@dataclass
class _CountingDigestRepo:
    """topic_id → TopicDigest 매핑. find_by_topics 호출 횟수와 인자를 기록한다."""

    by_topic: dict[str, TopicDigest] = field(default_factory=dict)
    call_count: int = 0
    last_topic_ids: list[str] | None = None

    async def find_by_topics(self, topic_ids: list[str], user_id: str) -> dict[str, TopicDigest]:
        self.call_count += 1
        self.last_topic_ids = list(topic_ids)
        return {tid: self.by_topic[tid] for tid in topic_ids if tid in self.by_topic}

    async def find_by_topic(self, topic_id: str, user_id: str):
        # 실수로 옛 경로(N+1)로 되돌아가면 여기가 불려 테스트가 잡아낸다.
        raise AssertionError("find_by_topic(단건) 이 호출됐다 — 배치 경로가 아니다")


def _digest(topic_id: str, watermark: str) -> TopicDigest:
    return TopicDigest(
        id=f"dig_{topic_id}",
        topic_id=topic_id,
        user_id="u1",
        status=DigestStatus.COMPLETED,
        watermark_date_key=watermark,
        created_at=_NOW,
    )


async def test_digest_lookup_is_a_single_batch_call_not_one_per_topic() -> None:
    topics = [_topic("t1"), _topic("t2"), _topic("t3")]
    digest_repo = _CountingDigestRepo(
        by_topic={"t1": _digest("t1", "2026-09-01"), "t3": _digest("t3", "2026-09-05")}
    )

    summaries = await GetTopicsUseCase(
        _ListRepo(topics), digest_repo, _EmptyMatcher()
    ).execute(GetTopicsQuery(user_id="u1"))

    assert digest_repo.call_count == 1, "topic 수와 무관하게 정확히 한 번만 호출돼야 한다"
    assert sorted(digest_repo.last_topic_ids) == ["t1", "t2", "t3"]

    by_id = {s.topic.id: s for s in summaries}
    assert by_id["t1"].digest_watermark_date_key == "2026-09-01"
    assert by_id["t2"].digest_watermark_date_key is None, "digest 없는 topic 은 None 이어야 한다"
    assert by_id["t3"].digest_watermark_date_key == "2026-09-05"


async def test_no_digest_lookup_when_there_are_no_topics() -> None:
    digest_repo = _CountingDigestRepo()

    summaries = await GetTopicsUseCase(
        _ListRepo([]), digest_repo, _EmptyMatcher()
    ).execute(GetTopicsQuery(user_id="u1"))

    assert summaries == []
    assert digest_repo.call_count == 0
