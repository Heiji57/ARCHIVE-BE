"""토픽 ↔ 회고/할일 매칭.

digest 생성 워커(`worker/tasks/generate_digest.py`)가 쓰는 것과 **같은 규칙**(토픽 이름·설명
임베딩 → pgvector 코사인 유사도 검색)을 요청 경로(통계/소스/목록)에서 재사용한다.
차이는 limit 뿐 — 워커는 프롬프트 길이 때문에 topic_search_limit(50)으로 자르지만,
"이 주제에 몇 개가 묶여 있는가"는 topic_stats_match_limit 까지 센다.
"""
from typing import Any

from app.retrospective.domain.repositories.repository import IJournalEntryRepository
from app.shared.infrastructure.config.topic import TopicConfig
from app.todo.domain.repositories.repository import ITodoRepository
from app.topic.application.dtos.matching import MatchedEntry, MatchedTodo, TopicMatch
from app.topic.domain.models.topic import Topic
from app.topic.domain.repositories.repository import (
    IEntryChunkRepository,
    ITodoEmbeddingRepository,
)
from app.topic.infrastructure.ai.embedding_service import EmbeddingService
from app.topic.infrastructure.cache.topic_stats_cache import TopicStatsCache


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
    ) -> None:
        self._embedding_service = embedding_service
        self._chunk_repo = chunk_repo
        self._todo_emb_repo = todo_emb_repo
        self._entry_repo = entry_repo
        self._todo_repo = todo_repo
        self._cache = cache
        self._config = config

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

        batch_size = self._config.topic_embed_batch_size
        for start in range(0, len(misses), batch_size):
            batch = misses[start : start + batch_size]
            embeddings = await self._embedding_service.embed_batch(
                [_query_text(t) for t in batch]
            )
            for topic, embedding in zip(batch, embeddings):
                match = await self._resolve(user_id, embedding)
                await self._cache.set(
                    topic.id, topic.name, topic.description, _to_payload(match)
                )
                matches[topic.id] = match

        return matches

    async def _resolve(self, user_id: str, embedding: list[float]) -> TopicMatch:
        limit = self._config.topic_stats_match_limit
        threshold = self._config.topic_similarity_threshold

        chunks = await self._chunk_repo.search_similar(
            user_id=user_id,
            query_embedding=embedding,
            since_date_key=None,
            threshold=threshold,
            limit=limit,
        )
        todo_embeddings = await self._todo_emb_repo.search_similar(
            user_id=user_id,
            query_embedding=embedding,
            since_date_key=None,
            threshold=threshold,
            limit=limit,
        )

        # 한 회고가 여러 청크로 쪼개져 매칭될 수 있다 — entry 단위로 접는다.
        entry_ids = list(dict.fromkeys(c.entry_id for c in chunks))
        entries = await self._entry_repo.find_by_ids(user_id, entry_ids)
        todos = await self._todo_repo.find_by_ids(
            user_id, [t.todo_id for t in todo_embeddings]
        )

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
