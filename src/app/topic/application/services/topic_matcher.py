"""토픽 ↔ 회고/할일 매칭.

digest 생성 워커(`worker/tasks/generate_digest.py`)가 쓰는 것과 **같은 규칙**(토픽 이름·설명
임베딩 → pgvector 코사인 유사도 검색)을 요청 경로(통계/소스/목록)에서 재사용한다.

다른 것은 상한의 **값과 단위** 두 가지다. 워커는 프롬프트 길이 제약이라
topic_search_limit 만큼의 **청크**를 자르고, 매칭은 사용자에게 "회고 N건" 으로 보이므로
topic_stats_match_limit 만큼의 **회고**를 센다 — 청크로 자르면 단락을 길게 쓰는
사용자일수록 천장이 낮아진다(#10).
"""
from typing import Any

import structlog
from redis.asyncio.lock import Lock

from app.retrospective.domain.repositories.repository import IJournalEntryRepository
from app.shared.infrastructure.config.topic import TopicConfig
from app.todo.domain.repositories.repository import ITodoRepository
from app.topic.application.dtos.matching import MatchedEntry, MatchedTodo, TopicMatch
from app.topic.domain.models.topic import Topic
from app.topic.domain.repositories.repository import (
    IEntryChunkRepository,
    ITodoEmbeddingRepository,
    ITopicMatchTransaction,
)
from app.topic.infrastructure.ai.embedding_service import EmbeddingService
from app.topic.infrastructure.cache.topic_stats_cache import TopicStatsCache

_log = structlog.get_logger(__name__)


def _query_text(topic: Topic) -> str:
    # generate_digest.py 와 동일한 조합 — 매칭 규칙이 갈리면 통계와 문서 내용이 어긋난다.
    text = topic.name
    if topic.description:
        text += ": " + topic.description
    return text


def _to_payload(match: TopicMatch) -> dict[str, Any]:
    return {
        "entries": [
            {"id": e.id, "title": e.title, "date_key": e.date_key, "retro_type": e.retro_type}
            for e in match.entries
        ],
        "todos": [
            {
                "id": t.id,
                "title": t.title,
                "date_key": t.date_key,
                "status": t.status,
                "tags": t.tags,
            }
            for t in match.todos
        ],
    }


def _from_payload(payload: dict[str, Any]) -> TopicMatch:
    return TopicMatch(
        entries=[MatchedEntry(**e) for e in payload["entries"]],
        todos=[MatchedTodo(**t) for t in payload["todos"]],
    )


class TopicMatcher:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        chunk_repo: IEntryChunkRepository,
        todo_emb_repo: ITodoEmbeddingRepository,
        entry_repo: IJournalEntryRepository,
        todo_repo: ITodoRepository,
        cache: TopicStatsCache,
        config: TopicConfig,
        transaction: ITopicMatchTransaction,
    ) -> None:
        self._embedding_service = embedding_service
        self._chunk_repo = chunk_repo
        self._todo_emb_repo = todo_emb_repo
        self._entry_repo = entry_repo
        self._todo_repo = todo_repo
        self._cache = cache
        self._config = config
        self._transaction = transaction

    async def match(self, user_id: str, topic: Topic) -> TopicMatch:
        result = await self.match_many(user_id, [topic])
        return result[topic.id]

    async def match_many(self, user_id: str, topics: list[Topic]) -> dict[str, TopicMatch]:
        """캐시 미스인 토픽들의 임베딩을 한 번에 묶어 처리한다 (목록 화면의 N+1 방지)."""
        matches: dict[str, TopicMatch] = {}
        misses: list[Topic] = []

        for topic in topics:
            cached = await self._cache.get(topic.id, topic.name, topic.description)
            if cached is not None:
                matches[topic.id] = _from_payload(cached)
            else:
                misses.append(topic)

        if not misses:
            return matches

        # cache stampede 방지: 같은 topic 을 동시에 여러 요청(다른 탭, 중복 새로고침
        # 등)이 미스하면 각자 임베딩 API + DB 를 중복 호출한다. miss 마다 락을 시도해
        # 얻은 것만 이번 요청이 계산하고(locked), 못 얻은 것(waiting)은 보유자의 결과가
        # 캐시에 쓰이길 기다렸다가 재사용한다 — 단일 요청 안에서 여러 topic 이 함께
        # 미스하는 보통의 경우(첫 로딩 등)는 그대로 embed_batch 로 한 번에 처리된다.
        locked: list[Topic] = []
        locks: dict[str, Lock] = {}
        waiting: list[Topic] = []
        try:
            for topic in misses:
                lock = self._cache.lock(topic.id, topic.name, topic.description)
                if await lock.acquire(blocking=False):
                    locks[topic.id] = lock
                    locked.append(topic)
                else:
                    waiting.append(topic)
        except Exception:
            # 획득 시도 자체가 중간에 실패하면(예: Redis 커넥션 오류) 이미 얻어 둔
            # 락들이 release() 없이 새어나가 TTL 만료까지 다른 요청을 막는다.
            await self._release_locks(locks)
            raise

        try:
            batch_size = self._config.topic_embed_batch_size
            for start in range(0, len(locked), batch_size):
                batch = locked[start : start + batch_size]
                embeddings = await self._embedding_service.embed_batch(
                    [_query_text(t) for t in batch]
                )
                # strict=True: 임베딩 API 가 입력보다 적은 벡터를 돌려주면(부분 실패 등)
                # 뒤쪽 주제들이 matches 에서 조용히 빠지고, match() 의 result[topic.id]
                # 가 원인을 알 수 없는 KeyError → 무코드 500 이 됐다(#3). 배치를 원자적
                # 으로 실패시켜 총 실패와 같은 경로(GetTopicsUseCase 의 degrade, 그
                # 외엔 그대로 전파)를 타게 한다.
                for topic, embedding in zip(batch, embeddings, strict=True):
                    match = await self._resolve(user_id, embedding)
                    await self._cache.set(
                        topic.id, topic.name, topic.description, _to_payload(match)
                    )
                    matches[topic.id] = match
        finally:
            await self._release_locks(locks)

        for topic in waiting:
            cached = await self._cache.wait_for(
                topic.id,
                topic.name,
                topic.description,
                timeout=self._config.topic_match_wait_timeout_seconds,
            )
            if cached is not None:
                matches[topic.id] = _from_payload(cached)
                continue
            # 보유자가 타임아웃 안에 못 끝냈다(크래시 등) — 락 없이 직접 계산해
            # 안전망 역할을 한다. 다시 락을 시도하지 않는다 — 원래 보유자가 아직도
            # 갱신 중이라면 굳이 경합할 필요가 없다.
            embedding = await self._embedding_service.embed_text(_query_text(topic))
            match = await self._resolve(user_id, embedding)
            await self._cache.set(topic.id, topic.name, topic.description, _to_payload(match))
            matches[topic.id] = match

        return matches

    @staticmethod
    async def _release_locks(locks: dict[str, Lock]) -> None:
        """락 해제 하나가 실패해도 나머지는 마저 해제하고, 이미 전파 중인 예외를
        release 실패로 덮어써 원인을 가리지 않는다.

        `_resolve` 가 `lock_ttl_seconds` 보다 오래 걸리면 redis-py 의 `Lock.release()`
        가 `LockNotOwnedError` 를 던진다(이미 TTL 로 자동 해제된 상태) — 이 경우
        결과적으로 원하던 상태(락 없음)이므로 경고만 남기고 계속한다.
        """
        for topic_id, lock in locks.items():
            try:
                await lock.release()
            except Exception:
                _log.warning(
                    "topic_matcher.lock_release_failed", topic_id=topic_id, exc_info=True
                )

    async def _resolve(self, user_id: str, embedding: list[float]) -> TopicMatch:
        limit = self._config.topic_stats_match_limit
        threshold = self._config.topic_similarity_threshold

        # 벡터 검색 2회 + 그 결과의 엔티티 조회 2회를 하나의 SAVEPOINT 로 묶는다. 이 중
        # 하나라도 실패하면 여기까지만 되감기고, GetTopicsUseCase 처럼 실패를 삼키고
        # degrade 하는 호출자가 같은 세션으로 잇달아 여는 조회(예: digest watermark)가
        # InFailedSQLTransaction 으로 죽지 않는다.
        async with self._transaction.nested():
            # 매칭에 필요한 건 "어떤 회고·할일이 묶이는가" 뿐이다. 청크 본문(text)이나
            # 회고 본문(content)·할일의 반복/캘린더 컬럼은 읽지 않으므로 싣지 않는다.
            # 한 회고가 여러 청크로 쪼개지는 것도 DB 에서 접는다 — 회고마다 가장
            # 가까운 청크 기준으로 상위 N 개 **회고**를 고른다(청크 N 개가 아니다).
            entry_ids = await self._chunk_repo.search_similar_entry_ids(
                user_id=user_id,
                query_embedding=embedding,
                since_date_key=None,
                threshold=threshold,
                limit=limit,
            )
            todo_ids = await self._todo_emb_repo.search_similar_todo_ids(
                user_id=user_id,
                query_embedding=embedding,
                since_date_key=None,
                threshold=threshold,
                limit=limit,
            )

            entries = await self._entry_repo.find_meta_by_ids(user_id, entry_ids)
            todos = await self._todo_repo.find_meta_by_ids(user_id, todo_ids)

        return TopicMatch(
            entries=[
                MatchedEntry(
                    id=e.id,
                    title=e.title,
                    date_key=e.date_key,
                    retro_type=e.retro_type.value,
                )
                for e in entries
            ],
            todos=[
                MatchedTodo(
                    id=t.id,
                    title=t.title,
                    date_key=t.date_key,
                    status=t.status.value,
                    tags=list(t.tags),
                )
                for t in todos
            ],
        )
