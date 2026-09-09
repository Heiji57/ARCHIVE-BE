from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.domain.utils.id import generate_id
from app.todo.domain.models.value_objects import TaskStatus
from app.topic.domain.models.topic import (
    EmbeddingQueueItem,
    EntryChunk,
    SimilarChunk,
    SimilarTodo,
    TodoEmbedding,
)
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

# 매칭 대상 할일 상태 — not-start 는 "아직 한 일이 없다"라 주제 집계에서 제외한다.
_MATCHED_TODO_STATUSES = (TaskStatus.IN_PROGRESS.value, TaskStatus.DONE.value)


async def _fetch_in_savepoint(session: AsyncSession, stmt: Select[Any]) -> list[Row[Any]]:
    """벡터 검색을 SAVEPOINT 안에서 돌린다.

    Postgres 는 트랜잭션 안에서 문장 하나가 깨지면 트랜잭션 전체를 폐기한다. 이 검색은
    호출자가 실패를 삼키고 degrade 하도록 설계돼 있어서(`GetTopicsUseCase` 의 카운트),
    가드가 없으면 예외를 삼킨 뒤 같은 세션에서 이어지는 조회가 전부
    InFailedSQLTransaction 으로 죽는다 — 목록 API 가 500 이 된다. SAVEPOINT 로 감싸면
    실패가 이 문장까지만 되감기고 바깥 트랜잭션은 살아남는다.
    """
    async with session.begin_nested():
        return list((await session.execute(stmt)).all())


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
    ) -> list[SimilarChunk]:
        # 코사인 유사도 >= threshold 는 코사인 거리 <= 1 - threshold 와 동치. 거리 쪽으로
        # 세워야 <=> 연산자와 HNSW(vector_cosine_ops) 인덱스를 그대로 태울 수 있다.
        distance = EntryChunkModel.embedding.cosine_distance(query_embedding)
        conditions = [
            EntryChunkModel.user_id == user_id,
            EntryChunkModel.embedding.is_not(None),
            distance <= 1 - threshold,
        ]
        if since_date_key:
            conditions.append(EntryChunkModel.date_key >= since_date_key)

        # embedding 은 일부러 SELECT 하지 않는다 — 호출자(매칭/프롬프트 조립)가 쓰지 않는데
        # 행마다 768 float 을 실어오면 limit 만큼 그대로 낭비된다.
        stmt = (
            select(
                EntryChunkModel.id,
                EntryChunkModel.entry_id,
                EntryChunkModel.chunk_index,
                EntryChunkModel.text,
                EntryChunkModel.date_key,
            )
            .where(*conditions)
            .order_by(distance)
            .limit(limit)
        )

        rows = await _fetch_in_savepoint(self._session, stmt)
        return [
            SimilarChunk(
                id=row.id,
                entry_id=row.entry_id,
                chunk_index=row.chunk_index,
                text=row.text,
                date_key=row.date_key,
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
    ) -> list[SimilarTodo]:
        # 거리 부등식 변환·embedding 미조회·SAVEPOINT 이유는 EntryChunkRepository 쪽 주석 참고.
        distance = TodoEmbeddingModel.embedding.cosine_distance(query_embedding)
        conditions = [
            TodoEmbeddingModel.user_id == user_id,
            TodoEmbeddingModel.status.in_(_MATCHED_TODO_STATUSES),
            TodoEmbeddingModel.embedding.is_not(None),
            distance <= 1 - threshold,
        ]
        if since_date_key:
            conditions.append(TodoEmbeddingModel.date_key >= since_date_key)

        stmt = (
            select(
                TodoEmbeddingModel.id,
                TodoEmbeddingModel.todo_id,
                TodoEmbeddingModel.text,
                TodoEmbeddingModel.date_key,
                TodoEmbeddingModel.status,
            )
            .where(*conditions)
            .order_by(distance)
            .limit(limit)
        )

        rows = await _fetch_in_savepoint(self._session, stmt)
        return [
            SimilarTodo(
                id=row.id,
                todo_id=row.todo_id,
                text=row.text,
                date_key=row.date_key,
                status=row.status,
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
