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
# 자가 복구로 한 주기에 되돌릴 회고 수 상한 — 누락분이 많아도 한 번에 몰아치지 않게 한다.
_RECONCILE_LIMIT = 100


def _hard_split(text: str, max_chars: int) -> list[str]:
    """길이 상한만 적용해 자른다 — 문장 경계를 우선하되 min_chars 는 보지 않는다."""
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    current = ""
    for sent in text.split(". "):
        candidate = (current + ". " + sent).lstrip(". ")
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            parts.append(current)
        # 한 문장 자체가 상한을 넘으면 글자 수로 끊는다 (무한 루프 방지).
        while len(sent) > max_chars:
            parts.append(sent[:max_chars])
            sent = sent[max_chars:]
        current = sent
    if current:
        parts.append(current)
    return parts


def _split_chunks(content: str, max_chars: int, min_chars: int) -> list[str]:
    """단락 단위 청크 분할.

    `min_chars` 는 **긴 회고 안에서 의미 없는 짧은 단락(제목, "끝" 등)을 걸러내는**
    용도다 — "이 회고를 집계할지"를 정하는 값이 아니다. 모든 단락이 그 미만이라
    결과가 비면, 본문 전체를 하나의 의미 단위로 보고 길이 상한만 적용해 되돌린다.
    이 폴백이 없으면 짧은 회고는 임베딩이 아예 생성되지 않아 어떤 주제에도 매칭되지
    않는다 — 주제 집계에서 영구 누락된다 (#8).

    임계값을 0 으로 낮추는 대신 폴백을 쓰는 이유: 그러면 "제목", "끝" 같은 두 글자
    단락이 각각 독립 임베딩이 되어 매칭에 잡음이 된다. 짧은 회고는 통째로 하나의
    단위로 다루는 편이 임베딩 수도 적고 의미도 정확하다.
    """
    paras = [p.strip() for p in content.split("\n\n") if p.strip()]
    result = []
    for para in paras:
        if len(para) < min_chars:
            continue
        # 긴 단락은 문장 단위로 추가 분할. `_hard_split` 은 문장 하나가 상한을 넘는
        # 경우까지 글자 수로 끊어 주므로 결과가 항상 max_chars 이하다 — 예전에는
        # ". " 로 안 쪼개지는 긴 단락(마침표 뒤 줄바꿈만 있는 한국어 글이 흔하다)이
        # 통째로 청크가 되어 상한을 넘겼고, 임베딩 API 가 거절하면 큐 항목이 지워지지
        # 않아 5분마다 영원히 재시도됐다.
        result.extend(p for p in _hard_split(para, max_chars) if len(p) >= min_chars)

    if not result and paras:
        # 폴백 — 본문에 글자가 있는 한 반드시 청크 하나 이상을 돌려준다.
        return _hard_split(" ".join(paras), max_chars)
    return result


async def _process_batch(user_id_filter: str | None = None) -> int:
    """큐에서 한 배치를 처리하고 **큐에서 실제로 없어진** 항목 수를 반환한다.

    `len(items)` 가 아니라 진척(=삭제된 큐 항목)을 세는 게 중요하다. 항목 처리는
    per-item try/except 로 감싸져 있어 실패하면 큐에 그대로 남는데, `dequeue_batch`
    는 항상 가장 오래된 것부터 돌려주므로 영구히 실패하는 항목이 하나라도 있으면
    호출자의 `while count != 0` 루프가 그 항목을 무한히 다시 꺼내며 끝나지 않는다.
    진척을 반환하면 남은 게 실패 항목뿐일 때 0 이 되어 루프가 종료된다.
    """
    settings = get_settings()
    factory = get_worker_session_factory()
    cfg = settings.topic

    emb_service = EmbeddingService(settings.ai)

    async with factory.begin() as session:
        queue_repo = EmbeddingQueueRepository(session)
        items = await queue_repo.dequeue_batch(_BATCH_SIZE, user_id=user_id_filter)
        if not items:
            return 0

        completed = 0
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
                        completed += 1
                        continue

                    chunk_texts = _split_chunks(entry.content, cfg.topic_chunk_max_chars, cfg.topic_chunk_min_chars)
                    if not chunk_texts:
                        await queue_repo.delete(item.id)
                        completed += 1
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
                    completed += 1
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
                        completed += 1
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
                    completed += 1
                except Exception:
                    _log.exception("embed_stale.todo_failed", entity_id=item.entity_id)

    return completed


async def _drain() -> int:
    processed = 0
    while True:
        count = await _process_batch()
        if count == 0:
            return processed
        processed += count


async def _requeue_missing() -> int:
    """임베딩이 없는 회고를 큐에 되돌린다 — 큐 유실에 대한 자가 복구."""
    factory = get_worker_session_factory()
    async with factory.begin() as session:
        return await EmbeddingQueueRepository(session).enqueue_entries_missing_chunks(
            _RECONCILE_LIMIT
        )


@celery_app.task(name="worker.embed_stale", rate_limit="12/m")
async def embed_stale_task() -> None:
    """5분마다 실행 — embedding_queue 드레인 + 누락 회고 자가 복구.

    큐는 회고/할일 라우터에서만 채워지므로 워커 다운·큐 등록 실패·기능 도입 이전
    데이터는 재시도 경로가 없었다. 드레인 후 누락분을 되돌려 넣고 한 번 더 비운다 —
    다음 beat 를 기다리지 않고 이번 실행에서 처리된다.
    """
    processed = await _drain()

    requeued = await _requeue_missing()
    if requeued:
        processed += await _drain()

    _log.info("embed_stale.done", processed=processed, requeued=requeued)
