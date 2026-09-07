"""임베딩 큐 드레이너 — 5분마다 실행해 stale 항목을 일괄 임베딩."""
import asyncio
from datetime import datetime, timezone

import structlog

from app.shared.domain.utils.id import generate_id
from app.shared.infrastructure.config.settings import get_settings
from app.topic.infrastructure.ai.embedding_service import EmbeddingService
from app.topic.infrastructure.persistence.models.chunk_model import (  # noqa: F401 — SQLAlchemy metadata
    EmbeddingQueueModel,
    EntryChunkModel,
    TodoEmbeddingModel,
)
from app.topic.infrastructure.persistence.repositories.chunk_repo import (
    EmbeddingQueueRepository,
    EntryChunkRepository,
    TodoEmbeddingRepository,
)
from app.worker.celery_app import celery_app
from app.worker.db import get_worker_session_factory

_log = structlog.get_logger(__name__)

_BATCH_SIZE = 20


def _split_chunks(content: str, max_chars: int, min_chars: int) -> list[str]:
    """단락 단위 청크 분할."""
    paras = [p.strip() for p in content.split("\n\n") if p.strip()]
    result = []
    for para in paras:
        if len(para) < min_chars:
            continue
        if len(para) <= max_chars:
            result.append(para)
        else:
            # 긴 단락은 문장 단위로 추가 분할
            sentences = para.split(". ")
            current = ""
            for sent in sentences:
                candidate = (current + ". " + sent).lstrip(". ")
                if len(candidate) <= max_chars:
                    current = candidate
                else:
                    if current and len(current) >= min_chars:
                        result.append(current)
                    current = sent
            if current and len(current) >= min_chars:
                result.append(current)
    return result


async def _process_batch(user_id_filter: str | None = None) -> int:
    """큐에서 한 배치를 처리하고 처리된 항목 수를 반환한다."""
    settings = get_settings()
    factory = get_worker_session_factory()
    cfg = settings.topic

    emb_service = EmbeddingService(settings.ai)

    async with factory.begin() as session:
        queue_repo = EmbeddingQueueRepository(session)
        items = await queue_repo.dequeue_batch(_BATCH_SIZE, user_id=user_id_filter)
        if not items:
            return 0

        entry_items = [i for i in items if i.entity_type == "entry"]
        todo_items = [i for i in items if i.entity_type == "todo"]

        # ── Entry 청크 임베딩 ────────────────────────────────────────────────
        if entry_items:
            from app.retrospective.infrastructure.persistence.repositories.journal_entry_repo import (
                JournalEntryRepository,
            )
            entry_repo = JournalEntryRepository(session)
            chunk_repo = EntryChunkRepository(session)

            for item in entry_items:
                try:
                    entry = await entry_repo.find_by_id(item.entity_id, item.user_id)
                    if entry is None:
                        await queue_repo.delete(item.id)
                        continue

                    chunk_texts = _split_chunks(entry.content, cfg.topic_chunk_max_chars, cfg.topic_chunk_min_chars)
                    if not chunk_texts:
                        await queue_repo.delete(item.id)
                        continue

                    embeddings = await emb_service.embed_batch(chunk_texts)
                    now = datetime.now(timezone.utc)

                    from app.topic.domain.models.topic import EntryChunk
                    chunks = [
                        EntryChunk(
                            id=generate_id("chunk"),
                            entry_id=entry.id,
                            user_id=entry.user_id,
                            chunk_index=idx,
                            text=chunk_texts[idx],
                            date_key=entry.date_key,
                            embedding=embeddings[idx],
                            created_at=now,
                        )
                        for idx in range(len(chunk_texts))
                    ]
                    await chunk_repo.upsert_chunks(chunks)
                    await queue_repo.delete(item.id)
                except Exception:
                    _log.exception("embed_stale.entry_failed", entity_id=item.entity_id)

        # ── Todo 임베딩 ──────────────────────────────────────────────────────
        if todo_items:
            from app.todo.infrastructure.persistence.repositories.todo_repo import TodoRepository
            todo_repo = TodoRepository(session)
            todo_emb_repo = TodoEmbeddingRepository(session)

            for item in todo_items:
                try:
                    todo = await todo_repo.find_by_id(item.entity_id, item.user_id)
                    if todo is None:
                        await queue_repo.delete(item.id)
                        continue
                    text_parts = [todo.title]
                    if todo.description:
                        text_parts.append(todo.description)
                    if todo.tags:
                        text_parts.append(" ".join(todo.tags))
                    todo_text = " ".join(text_parts)

                    embedding = await emb_service.embed_text(todo_text)
                    now = datetime.now(timezone.utc)

                    from app.topic.domain.models.topic import TodoEmbedding
                    todo_emb = TodoEmbedding(
                        id=generate_id("todo_emb"),
                        todo_id=todo.id,
                        user_id=todo.user_id,
                        text=todo_text,
                        date_key=todo.date_key,
                        status=todo.status.value,
                        embedding=embedding,
                        created_at=now,
                    )
                    await todo_emb_repo.upsert(todo_emb)
                    await queue_repo.delete(item.id)
                except Exception:
                    _log.exception("embed_stale.todo_failed", entity_id=item.entity_id)

    return len(items)


@celery_app.task(name="worker.embed_stale", rate_limit="12/m")
async def embed_stale_task() -> None:
    """5분마다 실행 — embedding_queue 전체 드레인."""
    processed = 0
    while True:
        count = await _process_batch()
        if count == 0:
            break
        processed += count
    _log.info("embed_stale.done", processed=processed)
