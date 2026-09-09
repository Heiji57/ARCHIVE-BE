from collections import Counter
from dataclasses import dataclass, field

from app.todo.domain.models.value_objects import TaskStatus
from app.todo.domain.repositories.repository import TagCount
from app.topic.application.dtos.queries import GetTopicStatsQuery
from app.topic.application.services.topic_matcher import TopicMatcher
from app.topic.domain.exceptions.exceptions import TopicNotFoundException
from app.topic.domain.repositories.repository import ITopicDigestRepository, ITopicRepository

# 태그 칩은 상위 N개만 노출하고 나머지는 "+8" 로 접는다 — 잘리기 전 종류 수는
# tag_count_total 로 따로 내려준다.
_TAG_COUNT_LIMIT = 20


@dataclass(frozen=True)
class EntryCounts:
    daily: int = 0
    weekly: int = 0
    monthly: int = 0
    yearly: int = 0
    total: int = 0


@dataclass(frozen=True)
class TodoCounts:
    total: int = 0
    completed: int = 0


@dataclass(frozen=True)
class TopicStats:
    topic_id: str
    entry_counts: EntryCounts
    todo_counts: TodoCounts
    tag_counts: list[TagCount] = field(default_factory=list)
    tag_count_total: int = 0
    period_start_date_key: str | None = None
    period_end_date_key: str | None = None
    unreflected_entry_count: int = 0


class GetTopicStatsUseCase:
    def __init__(
        self,
        topic_repo: ITopicRepository,
        digest_repo: ITopicDigestRepository,
        matcher: TopicMatcher,
    ) -> None:
        self._topic_repo = topic_repo
        self._digest_repo = digest_repo
        self._matcher = matcher

    async def execute(self, query: GetTopicStatsQuery) -> TopicStats:
        topic = await self._topic_repo.find_by_id(query.topic_id, query.user_id)
        if topic is None:
            raise TopicNotFoundException()

        match = await self._matcher.match(query.user_id, topic)
        digest = await self._digest_repo.find_by_topic(query.topic_id, query.user_id)
        watermark = digest.watermark_date_key if digest else None

        by_type = Counter(e.retro_type for e in match.entries)
        entry_counts = EntryCounts(
            daily=by_type.get("daily", 0),
            weekly=by_type.get("weekly", 0),
            monthly=by_type.get("monthly", 0),
            yearly=by_type.get("yearly", 0),
            total=len(match.entries),
        )

        todo_counts = TodoCounts(
            total=len(match.todos),
            completed=sum(1 for t in match.todos if t.status == TaskStatus.DONE.value),
        )

        tag_counter = Counter(tag for t in match.todos for tag in t.tags)
        tag_counts = [
            TagCount(tag=tag, count=count)
            for tag, count in sorted(tag_counter.items(), key=lambda kv: (-kv[1], kv[0]))[
                :_TAG_COUNT_LIMIT
            ]
        ]

        date_keys = [e.date_key for e in match.entries] + [t.date_key for t in match.todos]

        # 워터마크 "이후"(초과) 작성된 회고 수. 재생성이 주제 전체를 다시 읽게 되면서
        # 워커의 증분 커서와 경계를 맞출 이유가 없어졌고, >= 로 두면 방금 정리한 직후에도
        # 그날 회고가 "미반영"으로 잡혀 배너가 이상해진다.
        unreflected = (
            len(match.entries)
            if watermark is None
            else sum(1 for e in match.entries if e.date_key > watermark)
        )

        return TopicStats(
            topic_id=topic.id,
            entry_counts=entry_counts,
            todo_counts=todo_counts,
            tag_counts=tag_counts,
            tag_count_total=len(tag_counter),
            period_start_date_key=min(date_keys) if date_keys else None,
            period_end_date_key=max(date_keys) if date_keys else None,
            unreflected_entry_count=unreflected,
        )
