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


@dataclass(frozen=True, kw_only=True)
class SimilarChunk:
    """벡터 검색이 돌려주는 회고 청크 — 임베딩을 **뺀** 읽기 모델.

    검색 결과를 `EntryChunk` 로 돌려주면 embedding=None 을 채워 넣게 되는데, 그러면
    "값이 없다"와 "안 실어왔다"가 구분되지 않아 나중에 조용히 틀린다. 매칭·프롬프트
    조립 어느 쪽도 임베딩을 읽지 않으므로 아예 타입에서 지운다 (768 float × limit 만큼의
    전송·역직렬화도 함께 사라진다).
    """

    id: str
    entry_id: str
    chunk_index: int
    text: str
    date_key: str  # YYYY-MM-DD


@dataclass(frozen=True, kw_only=True)
class SimilarTodo:
    """벡터 검색이 돌려주는 할일 — 임베딩을 뺀 읽기 모델. SimilarChunk 와 같은 이유."""

    id: str
    todo_id: str
    text: str
    date_key: str  # YYYY-MM-DD
    status: str  # TaskStatus value
