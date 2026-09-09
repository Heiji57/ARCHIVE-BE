from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.retrospective.infrastructure.persistence.models.journal_entry_model import (
    JournalEntryModel,
)
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

# 파이썬 str.strip() 이 제거하는 문자(= str.isspace() 가 True)를 모두 제외한 클래스.
# Postgres 의 [[:space:]] 만으로는 NBSP 등 유니코드 공백이 빠져 파이썬 쪽과 어긋난다.
_NON_BLANK_PATTERN = (
    r"[^[:space:]\u001C-\u001F\u0085\u00A0\u1680"
    r"\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]"
)


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

    @staticmethod
    def _match_clause(
        user_id: str,
        query_embedding: list[float],
        since_date_key: str | None,
        threshold: float,
    ) -> tuple[Any, list[Any]]:
        """거리식과 WHERE 조건을 한곳에서 만든다 — 조회 종류마다 복붙하면 갈린다."""
        # 코사인 유사도 >= threshold 는 코사인 거리 <= 1 - threshold 와 동치. 거리 쪽으로
        # 세워야 <=> 연산자와 HNSW(vector_cosine_ops) 인덱스를 그대로 태울 수 있다.
        distance = EntryChunkModel.embedding.cosine_distance(query_embedding)
        conditions: list[Any] = [
            EntryChunkModel.user_id == user_id,
            EntryChunkModel.embedding.is_not(None),
            distance <= 1 - threshold,
        ]
        if since_date_key:
            conditions.append(EntryChunkModel.date_key >= since_date_key)
        return distance, conditions

    async def search_similar_entry_ids(
        self,
        user_id: str,
        query_embedding: list[float],
        since_date_key: str | None,
        threshold: float,
        limit: int,
    ) -> list[str]:
        """매칭 전용 — 청크 본문 없이 회고 id 만. 주제 매칭은 text 를 읽지 않는다.

        `limit` 은 **회고** 상한이다 — 가장 가까운 청크 기준으로 상위 N 개 회고를
        고른다. 청크 상한이 아닌 이유(#10): 청크는 단락 길이에 따라 회고당 2~4개로
        갈리는 순수 내부 단위인데, 사용자에게 보이는 건 "회고 N건" 이다. 청크로 자르면
        (a) 글을 길게 쓰는 사용자일수록 카운트 천장이 낮아지고(회고당 4청크면 250건,
        2청크면 500건), (b) 청크가 많은 긴 회고 하나가 슬롯을 여러 개 차지해 다른
        회고를 목록에서 밀어낸다. 회고 단위로 자르면 누구에게나 천장이 같고 회고
        하나가 정확히 한 자리만 쓴다.

        `search_similar`(digest 프롬프트용)의 `limit` 은 여전히 **청크** 상한이다 —
        그쪽은 프롬프트 길이 제약이라 청크가 맞는 단위다.
        """
        distance, conditions = self._match_clause(
            user_id, query_embedding, since_date_key, threshold
        )
        # 회고마다 가장 가까운 청크의 거리로 순위를 매긴다.
        stmt = (
            select(EntryChunkModel.entry_id)
            .where(*conditions)
            .group_by(EntryChunkModel.entry_id)
            .order_by(func.min(distance))
            .limit(limit)
        )
        rows = await _fetch_in_savepoint(self._session, stmt)
        return [row.entry_id for row in rows]

    async def search_similar(
        self,
        user_id: str,
        query_embedding: list[float],
        since_date_key: str | None,
        threshold: float,
        limit: int,
    ) -> list[SimilarChunk]:
        distance, conditions = self._match_clause(
            user_id, query_embedding, since_date_key, threshold
        )

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

    @staticmethod
    def _match_clause(
        user_id: str,
        query_embedding: list[float],
        since_date_key: str | None,
        threshold: float,
    ) -> tuple[Any, list[Any]]:
        # 거리 부등식 변환·embedding 미조회·SAVEPOINT 이유는 EntryChunkRepository 쪽 주석 참고.
        distance = TodoEmbeddingModel.embedding.cosine_distance(query_embedding)
        conditions: list[Any] = [
            TodoEmbeddingModel.user_id == user_id,
            TodoEmbeddingModel.status.in_(_MATCHED_TODO_STATUSES),
            TodoEmbeddingModel.embedding.is_not(None),
            distance <= 1 - threshold,
        ]
        if since_date_key:
            conditions.append(TodoEmbeddingModel.date_key >= since_date_key)
        return distance, conditions

    async def search_similar_todo_ids(
        self,
        user_id: str,
        query_embedding: list[float],
        since_date_key: str | None,
        threshold: float,
        limit: int,
    ) -> list[str]:
        """매칭 전용 — 할일 id 만. 주제 매칭은 text 를 읽지 않는다.

        todo_id 는 이 테이블에서 유니크라 회고 청크와 달리 중복 제거가 필요 없다.
        """
        distance, conditions = self._match_clause(
            user_id, query_embedding, since_date_key, threshold
        )
        stmt = (
            select(TodoEmbeddingModel.todo_id)
            .where(*conditions)
            .order_by(distance)
            .limit(limit)
        )
        rows = await _fetch_in_savepoint(self._session, stmt)
        return [row.todo_id for row in rows]

    async def search_similar(
        self,
        user_id: str,
        query_embedding: list[float],
        since_date_key: str | None,
        threshold: float,
        limit: int,
    ) -> list[SimilarTodo]:
        distance, conditions = self._match_clause(
            user_id, query_embedding, since_date_key, threshold
        )

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

    async def enqueue_entries_missing_chunks(self, limit: int) -> int:
        # 본문에 "파이썬이 공백으로 보지 않는" 글자가 하나라도 있으면 _split_chunks 의
        # 폴백이 청크를 최소 하나 보장하므로, 여기 걸린 회고는 처리 후 다시 걸리지
        # 않는다. 공백뿐인 회고를 제외하는 이유가 그것 — 넣어도 청크가 안 생겨 매
        # 주기 되돌아오는 무한 churn 이 된다.
        #
        # `\S` 를 쓰지 않는 이유: Postgres 의 [[:space:]] 는 NBSP(U+00A0), FIGURE
        # SPACE(U+2007) 같은 유니코드 공백을 공백으로 치지 않는데 파이썬 str.strip()
        # 은 제거한다. 그 어긋남이 있으면 "DB 는 내용이 있다고 보는데 청킹은 아무것도
        # 못 만드는" 회고가 생겨 영원히 되돌아온다. 아래 클래스는 str.isspace() 가
        # True 인 문자 집합과 정확히 일치한다.
        missing = select(
            JournalEntryModel.id.label("entity_id"),
            JournalEntryModel.user_id.label("user_id"),
        ).where(
            JournalEntryModel.content.regexp_match(_NON_BLANK_PATTERN),
            ~select(EntryChunkModel.id)
            .where(EntryChunkModel.entry_id == JournalEntryModel.id)
            .exists(),
        ).order_by(JournalEntryModel.created_at.desc()).limit(limit)

        rows = (await self._session.execute(missing)).all()
        if not rows:
            return 0

        now = datetime.now(timezone.utc)
        stmt = pg_insert(EmbeddingQueueModel).values(
            [
                {
                    "id": generate_id("emb_q"),
                    "entity_type": "entry",
                    "entity_id": row.entity_id,
                    "user_id": row.user_id,
                    "created_at": now,
                }
                for row in rows
            ]
        ).on_conflict_do_nothing(constraint="uq_embedding_queue_entity")
        await self._session.execute(stmt)
        await self._session.flush()
        return len(rows)

    async def has_pending_for_user(self, user_id: str) -> bool:
        result = await self._session.execute(
            select(EmbeddingQueueModel.id)
            .where(EmbeddingQueueModel.user_id == user_id)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
