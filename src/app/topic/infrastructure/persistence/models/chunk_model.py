from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database.base import Base

_EMBEDDING_DIM = 768


class EntryChunkModel(Base):
    __tablename__ = "topic_entry_chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    entry_id: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    date_key: Mapped[str] = mapped_column(String(10), nullable=False)
    embedding: Mapped[list | None] = mapped_column(Vector(_EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("entry_id", "chunk_index", name="uq_entry_chunks_entry_idx"),
        Index("ix_entry_chunks_user_id", "user_id"),
        Index("ix_entry_chunks_user_date", "user_id", "date_key"),
        # HNSW cosine index for vector similarity search
        Index(
            "ix_entry_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class TodoEmbeddingModel(Base):
    __tablename__ = "topic_todo_embeddings"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    todo_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    date_key: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    embedding: Mapped[list | None] = mapped_column(Vector(_EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_todo_embeddings_user_id", "user_id"),
        Index("ix_todo_embeddings_user_date", "user_id", "date_key"),
        Index(
            "ix_todo_embeddings_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class EmbeddingQueueModel(Base):
    __tablename__ = "topic_embedding_queue"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'entry' | 'todo'
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uq_embedding_queue_entity"),
        Index("ix_embedding_queue_user_id", "user_id"),
    )
