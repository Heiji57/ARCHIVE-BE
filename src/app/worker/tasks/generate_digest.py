"""토픽 다이제스트 생성 Celery task.

흐름:
  1. mark in_progress
  2. 사용자의 embedding_queue 잔여 항목 사전 동기화
  3. 토픽 쿼리 벡터 생성
  4. entry chunk / todo embedding 유사도 검색 (주제 전체 — 최초/재생성 동일)
  5. 프롬프트 조립 — 소스를 접어 넣으며 in_progress 진행률 pub/sub 발행
  6. Gemini 로 마크다운 다이제스트 생성
  7. mark completed + watermark 갱신 + Redis pub/sub 알림
"""
import json
from collections.abc import Awaitable, Callable

import structlog
from celery import Task
from celery.exceptions import Retry
from celery.utils.time import get_exponential_backoff_interval
from redis.asyncio import Redis
from sqlalchemy.exc import SQLAlchemyError

from app.shared.domain.exceptions.external import (
    AIQuotaExceededException,
    AIServiceException,
    AIServiceUnavailableException,
)
from app.shared.domain.utils.period import today_in_tz
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
from app.user.domain.models.user import User
from app.user.infrastructure.persistence.repositories.user_repo import UserRepository
from app.worker.celery_app import celery_app
from app.worker.db import get_worker_session_factory
from app.worker.tasks.embed_stale import _process_batch

_log = structlog.get_logger(__name__)

_REDIS_CHANNEL = "topic:digest:{digest_id}"

_AI_RETRY_BACKOFF_FACTOR = 2
_AI_QUOTA_BACKOFF_FACTOR = 30  # 429 쿼터는 분 단위 윈도우 — generate_summary 와 동일 정책
_AI_RETRY_BACKOFF_MAX_SECONDS = 300

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


def _source_total(chunks: list, todos: list) -> int:
    """진행률의 분모 — 회고는 청크가 아니라 엔트리 단위로 센다(FE 가 "회고 N개"로 표시)."""
    return len({c.entry_id for c in chunks}) + len(todos)


def _watermark_key_for_user(user: User | None) -> str:
    """digest watermark 에 찍을 날짜 — 사용자의 로컬 "오늘".

    watermark 는 `date_key`(회고 저장 시점의 사용자 로컬 날짜)와 같은 축으로 비교되는
    값이다 (`get_topic_stats.py` 의 unreflected 계산). 서버 UTC 로 찍으면 UTC+ 사용자가
    자정 근처에 정리를 생성할 때 방금 쓴 오늘자 회고가 즉시 "미반영"으로 잡힌다.
    사용자를 찾지 못하면(탈퇴 등 예외적 상황) UTC 로 폴백한다.
    """
    return today_in_tz(user.timezone if user is not None else "UTC").isoformat()


async def _build_prompt(
    topic_name: str,
    topic_description: str,
    chunks: list,
    todos: list,
    on_source: Callable[[int], Awaitable[None]] | None = None,
) -> str:
    """프롬프트를 조립하며, 소스 하나를 접어 넣을 때마다 on_source(누적 처리 수)를 호출한다."""
    lines = [_SYSTEM_PROMPT, "", f"## Topic: {topic_name}"]
    if topic_description:
        lines.append(f"Description: {topic_description}")

    processed = 0

    if chunks:
        lines += ["", "### Journal Entry Excerpts"]
        # chunks 는 유사도(코사인 거리) 순으로 온다 — entry_id 로 묶여 있지 않다.
        # 정렬 없이 순서대로 훑으면, 이미 헤딩을 찍은 entry 의 뒤늦게 나온 청크가
        # 방금 헤딩을 찍은 "다른" entry 밑에 잘못 붙는다. entry 등장 순서(최초로
        # 나온 순 = 그 entry 의 가장 유사한 청크 기준)는 그대로 보존하고, 같은
        # entry 안에서만 chunk_index 로 정렬해 재배치한다.
        entry_order: dict[str, int] = {}
        for chunk in chunks:
            entry_order.setdefault(chunk.entry_id, len(entry_order))
        chunks = sorted(chunks, key=lambda c: (entry_order[c.entry_id], c.chunk_index))

        # Group by entry_id to avoid repeating date_key
        seen: dict[str, str] = {}  # entry_id -> date_key
        for chunk in chunks:
            if chunk.entry_id not in seen:
                seen[chunk.entry_id] = chunk.date_key
                lines.append(f"\n**{chunk.date_key}**")
                processed += 1
                if on_source is not None:
                    await on_source(processed)
            lines.append(f"- {chunk.text}")

    if todos:
        lines += ["", "### Related Todos"]
        for todo in todos:
            lines.append(f"- [{todo.status}] ({todo.date_key}) {todo.text}")
            processed += 1
            if on_source is not None:
                await on_source(processed)

    lines += ["", "---", "", "Generate a markdown digest for this topic based on the above content."]
    return "\n".join(lines)


@celery_app.task(
    name="worker.generate_digest",
    bind=True,
    # AI 일시 장애는 본문에서 self.retry() 로 재시도한다. `autoretry_for` 는
    # celery_aio_pool 의 async task 에 작동하지 않는다 (generate_summary 의
    # SummaryRowNotYetVisibleError docstring 참고) — 예전 설정은 재시도를 한 번도 못 했다.
    max_retries=3,
)
async def generate_digest_task(self: Task, digest_id: str, topic_id: str, user_id: str) -> None:
    settings = get_settings()
    factory = get_worker_session_factory()
    cfg: TopicConfig = settings.topic

    # T1: mark in_progress
    async with factory.begin() as session:
        digest_repo = TopicDigestRepository(session)
        digest = await digest_repo.find_by_id(digest_id, user_id)
        if digest is None:
            return
        # 중복 실행 방어. 단 self.retry() 로 다시 온 실행은 직전 시도가 IN_PROGRESS 로
        # 남겨 둔 자기 자신이므로 통과시켜야 한다 — 막으면 재시도가 즉시 끝나 영구 IN_PROGRESS.
        if digest.status == DigestStatus.IN_PROGRESS and self.request.retries == 0:
            return
        await digest_repo.update_status(digest_id, DigestStatus.IN_PROGRESS)

    # 사전 동기화: 이 사용자의 embedding_queue 잔여 항목 처리
    try:
        while True:
            count = await _process_batch(user_id)
            if count == 0:
                break
    except (AIServiceException, SQLAlchemyError):
        # best-effort — 실패해도 이미 임베딩된 소스로 생성을 계속한다.
        _log.warning("generate_digest.pre_sync_failed", digest_id=digest_id, exc_info=True)

    redis = Redis.from_url(settings.redis.cache_url, decode_responses=True)

    try:
        # 중첩 try — self.retry() 가 재시도 소진 시 원본 exc 를 재발생시킬 때, 바깥 try 의
        # except 절들이 그 예외를 새로 매칭하도록 AI 재시도 분기를 본문 안에 둔다
        # (형제 except 로 두면 FAILED 마킹을 건너뛴다 — generate_summary 에서 재현된 회귀).
        try:
            async with factory.begin() as session:
                topic_repo = TopicRepository(session)
                topic = await topic_repo.find_by_id(topic_id, user_id)
                if topic is None:
                    await TopicDigestRepository(session).update_status(
                        digest_id, DigestStatus.FAILED
                    )
                    return

                user = await UserRepository(session).find_by_id(user_id)
                today_key = _watermark_key_for_user(user)

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
                    # 재생성도 최초 생성과 동일하게 주제 전체를 다시 읽는다 — watermark 이후
                    # 증분만 읽으면 재생성할수록 문서가 최근 내용만 다루도록 좁아진다.
                    since_date_key=None,
                    threshold=cfg.topic_similarity_threshold,
                    limit=cfg.topic_search_limit,
                )
                todos = await todo_emb_repo.search_similar(
                    user_id=user_id,
                    query_embedding=query_embedding,
                    # 재생성도 최초 생성과 동일하게 주제 전체를 다시 읽는다 — watermark 이후
                    # 증분만 읽으면 재생성할수록 문서가 최근 내용만 다루도록 좁아진다.
                    since_date_key=None,
                    threshold=cfg.topic_similarity_threshold,
                    limit=cfg.topic_search_limit,
                )

            # 진행률 이벤트 — 소스를 프롬프트에 접어 넣는 실제 진척을 배치 단위로 흘린다.
            # (AI 생성 구간 자체는 단일 호출이라 더 잘게 쪼개지지 않는다)
            total_sources = _source_total(chunks, todos)
            progress_batch = cfg.topic_digest_progress_batch_size

            async def publish_progress(processed: int) -> None:
                if processed % progress_batch and processed != total_sources:
                    return
                await redis.publish(
                    _REDIS_CHANNEL.format(digest_id=digest_id),
                    json.dumps(
                        {"status": "in_progress", "processed": processed, "total": total_sources}
                    ),
                )

            await publish_progress(0)
            prompt = await _build_prompt(
                topic.name, topic.description, chunks, todos, on_source=publish_progress
            )

            # AI 호출 — DB transaction 밖
            from app.topic.infrastructure.ai.gemini_client import TopicGeminiClient
            gemini = TopicGeminiClient(settings.ai)
            content = await gemini.generate(prompt)

            # T2: complete + watermark. watermark 는 이제 "어디까지 읽었나"(증분 커서)가 아니라
            # "이 문서가 언제 기준인가"를 뜻한다 — FE 배너/미반영 개수 계산의 기준점.
            async with factory.begin() as session:
                digest_repo = TopicDigestRepository(session)
                await digest_repo.update_status(digest_id, DigestStatus.COMPLETED, content)
                await digest_repo.update_watermark(digest_id, today_key)

        except AIServiceUnavailableException as exc:
            countdown = get_exponential_backoff_interval(
                factor=(
                    _AI_QUOTA_BACKOFF_FACTOR
                    if isinstance(exc, AIQuotaExceededException)
                    else _AI_RETRY_BACKOFF_FACTOR
                ),
                retries=self.request.retries,
                maximum=_AI_RETRY_BACKOFF_MAX_SECONDS,
                full_jitter=True,
            )
            raise self.retry(exc=exc, countdown=countdown) from exc

        await redis.publish(
            _REDIS_CHANNEL.format(digest_id=digest_id),
            json.dumps({"status": "completed"}),
        )

    except Retry:
        # 재시도 예약됨 — FAILED 마킹·failed publish 를 하면 재시도 성공 전에 FE 가 실패로 본다.
        raise
    except Exception as exc:
        # 태스크 최상위 경계 — 어떤 실패든 FAILED 로 확정해야 영구 IN_PROGRESS 를 막는다.
        _log.exception("generate_digest.failed", digest_id=digest_id)
        try:
            async with factory.begin() as session:
                await TopicDigestRepository(session).update_status(digest_id, DigestStatus.FAILED)
        except SQLAlchemyError:
            _log.exception("generate_digest.mark_failed_failed", digest_id=digest_id)
        await redis.publish(
            _REDIS_CHANNEL.format(digest_id=digest_id),
            json.dumps({"status": "failed"}),
        )
        raise exc
    finally:
        await redis.aclose()
