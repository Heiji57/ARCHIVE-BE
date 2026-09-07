from datetime import datetime, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.domain.utils.id import generate_id
from app.topic.domain.models.topic import EntryChunk, EmbeddingQueueItem, TodoEmbedding
from app.topic.domain.repositories.repository import (
    IEmbeddingQueueRepository,
    IEntryChunkRepository,
    ITodoEmbeddingRepository,
)
from app.topic.infrastructure.persistence.models.chunk_model import (
    EmbeddingQueueModel,
    EntryChunkModel,
    TodoEmbeddingModel,
)


class EntryChunkRepository(IEntryChunkRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_chunks(self, chunks: list[EntryChunk]) -> None:
        if not chunks:
            return
        for chunk in chunks:
            stmt = pg_insert(EntryChunkModel).values(
                id=chunk.id,
                entry_id=chunk.entry_id,
                user_id=chunk.user_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                date_key=chunk.date_key,
                embedding=chunk.embedding,
                created_at=chunk.created_at,
            ).on_conflict_do_update(
                constraint="uq_entry_chunks_entry_idx",
                set_={
                    "text": chunk.text,
                    "date_key": chunk.date_key,
                    "embedding": chunk.embedding,
                    "created_at": chunk.created_at,
                },
            )
            await self._session.execute(stmt)
        await self._session.flush()

    async def delete_by_entry(self, entry_id: str) -> None:
        await self._session.execute(
            delete(EntryChunkModel).where(EntryChunkModel.entry_id == entry_id)
        )
        await self._session.flush()

    async def search_similar(
        self,
        user_id: str,
        query_embedding: list[float],
        since_date_key: str | None,
        threshold: float,
        limit: int,
    ) -> list[EntryChunk]:
        emb_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
        if since_date_key:
            result = await self._session.execute(
                text(
                    "SELECT id, entry_id, user_id, chunk_index, text, date_key, embedding, created_at "
                    "FROM topic_entry_chunks "
                    "WHERE user_id = :user_id "
                    "  AND date_key >= :since "
                    "  AND embedding IS NOT NULL "
                    "  AND 1 - (embedding <=> :emb::vector) >= :threshold "
                    "ORDER BY embedding <=> :emb::vector "
                    "LIMIT :limit"
                ),
                {"user_id": user_id, "since": since_date_key, "emb": emb_str, "threshold": threshold, "limit": limit},
            )
        else:
            result = await self._session.execute(
                text(
                    "SELECT id, entry_id, user_id, chunk_index, text, date_key, embedding, created_at "
                    "FROM topic_entry_chunks "
                    "WHERE user_id = :user_id "
                    "  AND embedding IS NOT NULL "
                    "  AND 1 - (embedding <=> :emb::vector) >= :threshold "
                    "ORDER BY embedding <=> :emb::vector "
                    "LIMIT :limit"
                ),
                {"user_id": user_id, "emb": emb_str, "threshold": threshold, "limit": limit},
            )
        rows = result.fetchall()
        return [
            EntryChunk(
                id=row.id,
                entry_id=row.entry_id,
                user_id=row.user_id,
                chunk_index=row.chunk_index,
                text=row.text,
                date_key=row.date_key,
                embedding=list(row.embedding) if row.embedding is not None else None,
                created_at=row.created_at,
            )
            for row in rows
        ]


class TodoEmbeddingRepository(ITodoEmbeddingRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, embedding: TodoEmbedding) -> None:
        stmt = pg_insert(TodoEmbeddingModel).values(
            id=embedding.id,
            todo_id=embedding.todo_id,
            user_id=embedding.user_id,
            text=embedding.text,
            date_key=embedding.date_key,
            status=embedding.status,
            embedding=embedding.embedding,
            created_at=embedding.created_at,
        ).on_conflict_do_update(
            index_elements=["todo_id"],
            set_={
                "text": embedding.text,
                "date_key": embedding.date_key,
                "status": embedding.status,
                "embedding": embedding.embedding,
            },
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def delete_by_todo(self, todo_id: str) -> None:
        await self._session.execute(
            delete(TodoEmbeddingModel).where(TodoEmbeddingModel.todo_id == todo_id)
        )
        await self._session.flush()

    async def search_similar(
        self,
        user_id: str,
        query_embedding: list[float],
        since_date_key: str | None,
        threshold: float,
        limit: int,
    ) -> list[TodoEmbedding]:
        emb_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
        if since_date_key:
            result = await self._session.execute(
                text(
                    "SELECT id, todo_id, user_id, text, date_key, status, embedding, created_at "
                    "FROM topic_todo_embeddings "
                    "WHERE user_id = :user_id "
                    "  AND date_key >= :since "
                    "  AND status IN ('in_progress', 'done') "
                    "  AND embedding IS NOT NULL "
                    "  AND 1 - (embedding <=> :emb::vector) >= :threshold "
                    "ORDER BY embedding <=> :emb::vector "
                    "LIMIT :limit"
                ),
                {"user_id": user_id, "since": since_date_key, "emb": emb_str, "threshold": threshold, "limit": limit},
            )
        else:
            result = await self._session.execute(
                text(
                    "SELECT id, todo_id, user_id, text, date_key, status, embedding, created_at "
                    "FROM topic_todo_embeddings "
                    "WHERE user_id = :user_id "
                    "  AND status IN ('in_progress', 'done') "
                    "  AND embedding IS NOT NULL "
                    "  AND 1 - (embedding <=> :emb::vector) >= :threshold "
                    "ORDER BY embedding <=> :emb::vector "
                    "LIMIT :limit"
                ),
                {"user_id": user_id, "emb": emb_str, "threshold": threshold, "limit": limit},
            )
        rows = result.fetchall()
        return [
            TodoEmbedding(
                id=row.id,
                todo_id=row.todo_id,
                user_id=row.user_id,
                text=row.text,
                date_key=row.date_key,
                status=row.status,
                embedding=list(row.embedding) if row.embedding is not None else None,
                created_at=row.created_at,
            )
            for row in rows
        ]


class EmbeddingQueueRepository(IEmbeddingQueueRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, entity_type: str, entity_id: str, user_id: str) -> None:
        now = datetime.now(timezone.utc)
        stmt = pg_insert(EmbeddingQueueModel).values(
            id=generate_id("emb_q"),
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            created_at=now,
        ).on_conflict_do_update(
            constraint="uq_embedding_queue_entity",
            set_={"user_id": user_id, "updated_at": now},
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def dequeue_batch(self, limit: int, user_id: str | None = None) -> list[EmbeddingQueueItem]:
        stmt = select(EmbeddingQueueModel).order_by(EmbeddingQueueModel.created_at.asc())
        if user_id is not None:
            stmt = stmt.where(EmbeddingQueueModel.user_id == user_id)
        result = await self._session.execute(stmt.limit(limit))
        return [
            EmbeddingQueueItem(
                id=m.id,
                entity_type=m.entity_type,
                entity_id=m.entity_id,
                user_id=m.user_id,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m in result.scalars().all()
        ]

    async def delete(self, item_id: str) -> None:
        await self._session.execute(
            delete(EmbeddingQueueModel).where(EmbeddingQueueModel.id == item_id)
        )
        await self._session.flush()

    async def has_pending_for_user(self, user_id: str) -> bool:
        result = await self._session.execute(
            select(EmbeddingQueueModel.id)
            .where(EmbeddingQueueModel.user_id == user_id)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
