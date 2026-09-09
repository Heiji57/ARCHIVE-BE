from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from typing import Any

from app.topic.domain.models.topic import (
    EmbeddingQueueItem,
    EntryChunk,
    SimilarChunk,
    SimilarTodo,
    TodoEmbedding,
    Topic,
    TopicDigest,
)
from app.topic.domain.models.value_objects import DigestStatus


class ITopicRepository(ABC):
    @abstractmethod
    async def save(self, topic: Topic) -> Topic: ...

    @abstractmethod
    async def find_by_id(self, topic_id: str, user_id: str) -> Topic | None: ...

    @abstractmethod
    async def find_all_by_user(self, user_id: str) -> list[Topic]: ...

    @abstractmethod
    async def delete(self, topic_id: str, user_id: str) -> None: ...

    @abstractmethod
    async def exists_by_name(self, user_id: str, name: str) -> bool: ...

    @abstractmethod
    async def count_by_user(self, user_id: str) -> int: ...


class ITopicDigestRepository(ABC):
    @abstractmethod
    async def save(self, digest: TopicDigest) -> TopicDigest: ...

    @abstractmethod
    async def find_by_topic(self, topic_id: str, user_id: str) -> TopicDigest | None: ...

    @abstractmethod
    async def find_by_id(self, digest_id: str, user_id: str) -> TopicDigest | None: ...

    @abstractmethod
    async def update_status(
        self,
        digest_id: str,
        status: DigestStatus,
        content: str | None = None,
    ) -> None: ...

    @abstractmethod
    async def update_watermark(self, digest_id: str, watermark_date_key: str) -> None: ...


class IEntryChunkRepository(ABC):
    @abstractmethod
    async def upsert_chunks(self, chunks: list[EntryChunk]) -> None: ...

    @abstractmethod
    async def delete_by_entry(self, entry_id: str) -> None: ...

    @abstractmethod
    async def search_similar(
        self,
        user_id: str,
        query_embedding: list[float],
        since_date_key: str | None,
        threshold: float,
        limit: int,
    ) -> list[SimilarChunk]: ...


class ITodoEmbeddingRepository(ABC):
    @abstractmethod
    async def upsert(self, embedding: TodoEmbedding) -> None: ...

    @abstractmethod
    async def delete_by_todo(self, todo_id: str) -> None: ...

    @abstractmethod
    async def search_similar(
        self,
        user_id: str,
        query_embedding: list[float],
        since_date_key: str | None,
        threshold: float,
        limit: int,
    ) -> list[SimilarTodo]: ...


class IEmbeddingQueueRepository(ABC):
    @abstractmethod
    async def enqueue(self, entity_type: str, entity_id: str, user_id: str) -> None: ...

    @abstractmethod
    async def dequeue_batch(self, limit: int, user_id: str | None = None) -> list[EmbeddingQueueItem]: ...

    @abstractmethod
    async def delete(self, item_id: str) -> None: ...

    @abstractmethod
    async def has_pending_for_user(self, user_id: str) -> bool: ...


class ITopicMatchTransaction(ABC):
    """TopicMatcher 가 여러 리포지터리 호출을 하나의 실패 경계로 묶기 위한 좁은 포트.

    `TopicMatcher._resolve` 는 entry chunk/todo 벡터 검색과 그 결과의 엔티티 조회
    (`find_by_ids`)를 같은 요청 세션에서 잇달아 부른다. Postgres 는 문장 하나가 깨지면
    트랜잭션 전체를 폐기하므로, `GetTopicsUseCase` 처럼 매칭 실패를 삼키고 degrade 하는
    호출자가 그 뒤에 같은 세션으로 여는 조회(예: digest watermark)까지 함께 죽는다.
    응용 계층은 세션을 직접 들고 있지 않으므로, 이 블록만 SAVEPOINT 로 감쌀 수 있게
    최소한의 트랜잭션 경계만 노출한다 — 구체적인 세션/SAVEPOINT 구현은 인프라에 둔다.
    """

    @abstractmethod
    def nested(self) -> AbstractAsyncContextManager[Any]:
        """실패 시 이 블록까지만 되감고, 성공 시 그대로 커밋 대상에 편입되는 경계."""
        ...
