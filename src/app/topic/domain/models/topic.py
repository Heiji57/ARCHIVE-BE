from dataclasses import dataclass

from app.shared.domain.models.base import BaseEntity
from app.topic.domain.models.value_objects import DigestStatus


@dataclass(kw_only=True)
class Topic(BaseEntity):
    user_id: str
    name: str  # max 100 chars
    description: str = ""  # max 500 chars


@dataclass(kw_only=True)
class TopicDigest(BaseEntity):
    topic_id: str
    user_id: str
    status: DigestStatus
    content: str | None = None
    watermark_date_key: str | None = None  # YYYY-MM-DD, last processed date


@dataclass(kw_only=True)
class EntryChunk(BaseEntity):
    entry_id: str
    user_id: str
    chunk_index: int
    text: str
    date_key: str  # YYYY-MM-DD (from entry), for watermark filtering
    embedding: list[float] | None = None


@dataclass(kw_only=True)
class TodoEmbedding(BaseEntity):
    todo_id: str
    user_id: str
    text: str  # title + description + tags
    date_key: str  # YYYY-MM-DD (todo's date_key), for watermark filtering
    status: str  # TaskStatus value, for filtering in_progress/done
    embedding: list[float] | None = None


@dataclass(kw_only=True)
class EmbeddingQueueItem(BaseEntity):
    entity_type: str  # 'entry' | 'todo'
    entity_id: str
    user_id: str
