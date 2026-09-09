from abc import ABC, abstractmethod

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
