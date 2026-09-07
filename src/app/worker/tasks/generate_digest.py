"""토픽 다이제스트 생성 Celery task.

흐름:
  1. mark in_progress
  2. 사용자의 embedding_queue 잔여 항목 사전 동기화
  3. 토픽 쿼리 벡터 생성
  4. entry chunk / todo embedding 유사도 검색 (watermark 이후)
  5. Gemini 로 마크다운 다이제스트 생성
  6. mark completed + watermark 갱신 + Redis pub/sub 알림
"""
import json
from datetime import datetime, timezone

import httpx
import structlog
from google.genai import errors as genai_errors
from redis.asyncio import Redis

from app.shared.infrastructure.config.settings import get_settings
from app.shared.infrastructure.config.topic import TopicConfig
from app.topic.domain.models.value_objects import DigestStatus
from app.topic.infrastructure.ai.embedding_service import EmbeddingService
from app.topic.infrastructure.persistence.repositories.chunk_repo import (
    EntryChunkRepository,
    EmbeddingQueueRepository,
    TodoEmbeddingRepository,
)
from app.topic.infrastructure.persistence.repositories.topic_repo import (
    TopicDigestRepository,
    TopicRepository,
)
from app.worker.celery_app import celery_app
from app.worker.db import get_worker_session_factory
from app.worker.tasks.embed_stale import _process_batch

_log = structlog.get_logger(__name__)

_REDIS_CHANNEL = "topic:digest:{digest_id}"

_SYSTEM_PROMPT = """You are a concise personal productivity assistant.
Given a user's topic and relevant excerpts from their journal entries and todos,
generate a markdown digest summarizing what they have been doing related to this topic.

Requirements:
- Use markdown headings, bullet points, and concise prose.
- Group information meaningfully (e.g., by subtask, theme, or time period).
- Keep it actionable and relevant.
- Write in the same language as the source content.
- Do not invent information not present in the provided content.
"""


def _build_prompt(topic_name: str, topic_description: str, chunks: list, todos: list) -> str:
    lines = [_SYSTEM_PROMPT, "", f"## Topic: {topic_name}"]
    if topic_description:
        lines.append(f"Description: {topic_description}")

    if chunks:
        lines += ["", "### Journal Entry Excerpts"]
        # Group by entry_id to avoid repeating date_key
        seen: dict[str, str] = {}  # entry_id -> date_key
        for chunk in chunks:
            if chunk.entry_id not in seen:
                seen[chunk.entry_id] = chunk.date_key
                lines.append(f"\n**{chunk.date_key}**")
            lines.append(f"- {chunk.text}")

    if todos:
        lines += ["", "### Related Todos"]
        for todo in todos:
            lines.append(f"- [{todo.status}] ({todo.date_key}) {todo.text}")

    lines += ["", "---", "", "Generate a markdown digest for this topic based on the above content."]
    return "\n".join(lines)


@celery_app.task(
    name="worker.generate_digest",
    autoretry_for=(genai_errors.ServerError, httpx.TimeoutException),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
async def generate_digest_task(digest_id: str, topic_id: str, user_id: str) -> None:
    settings = get_settings()
    factory = get_worker_session_factory()
    cfg: TopicConfig = settings.topic

    today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # T1: mark in_progress
    async with factory.begin() as session:
        digest_repo = TopicDigestRepository(session)
        digest = await digest_repo.find_by_id(digest_id, user_id)
        if digest is None:
            return
        if digest.status == DigestStatus.IN_PROGRESS:
            return  # 중복 실행 방어
        await digest_repo.update_status(digest_id, DigestStatus.IN_PROGRESS)
        watermark = digest.watermark_date_key

    # 사전 동기화: 이 사용자의 embedding_queue 잔여 항목 처리
    try:
        while True:
            count = await _process_batch(user_id)
            if count == 0:
                break
    except Exception:
        _log.warning("generate_digest.pre_sync_failed", digest_id=digest_id)

    redis = Redis.from_url(settings.redis.cache_url, decode_responses=True)

    try:
        async with factory.begin() as session:
            topic_repo = TopicRepository(session)
            topic = await topic_repo.find_by_id(topic_id, user_id)
            if topic is None:
                await TopicDigestRepository(session).update_status(digest_id, DigestStatus.FAILED)
                return

            emb_service = EmbeddingService(settings.ai)
            query_text = topic.name
            if topic.description:
                query_text += ": " + topic.description
            query_embedding = await emb_service.embed_text(query_text)

            chunk_repo = EntryChunkRepository(session)
            todo_emb_repo = TodoEmbeddingRepository(session)

            chunks = await chunk_repo.search_similar(
                user_id=user_id,
                query_embedding=query_embedding,
                since_date_key=watermark,
                threshold=cfg.topic_similarity_threshold,
                limit=cfg.topic_search_limit,
            )
            todos = await todo_emb_repo.search_similar(
                user_id=user_id,
                query_embedding=query_embedding,
                since_date_key=watermark,
                threshold=cfg.topic_similarity_threshold,
                limit=cfg.topic_search_limit,
            )

        prompt = _build_prompt(topic.name, topic.description, chunks, todos)

        # AI 호출 — DB transaction 밖
        from app.topic.infrastructure.ai.gemini_client import TopicGeminiClient
        gemini = TopicGeminiClient(settings.ai)
        content = await gemini.generate(prompt)

        # T2: complete + watermark
        async with factory.begin() as session:
            digest_repo = TopicDigestRepository(session)
            await digest_repo.update_status(digest_id, DigestStatus.COMPLETED, content)
            await digest_repo.update_watermark(digest_id, today_key)

        await redis.publish(
            _REDIS_CHANNEL.format(digest_id=digest_id),
            json.dumps({"status": "completed"}),
        )

    except Exception as exc:
        _log.exception("generate_digest.failed", digest_id=digest_id)
        try:
            async with factory.begin() as session:
                await TopicDigestRepository(session).update_status(digest_id, DigestStatus.FAILED)
        except Exception:
            pass
        await redis.publish(
            _REDIS_CHANNEL.format(digest_id=digest_id),
            json.dumps({"status": "failed"}),
        )
        raise exc
    finally:
        await redis.aclose()
