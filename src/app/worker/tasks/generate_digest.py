"""토픽 다이제스트 생성 Celery task.

흐름:
  1. mark in_progress
  2. 사용자의 embedding_queue 잔여 항목 사전 동기화
  3. 토픽 쿼리 벡터 생성
  4. 전체/증분 판정 후 entry chunk(+앞뒤 청크) / todo embedding 유사도 검색
  5. 프롬프트 조립 — 소스를 접어 넣으며 in_progress 진행률 pub/sub 발행
  6. Gemini 로 마크다운 다이제스트 생성
  7. mark completed + watermark·증분 상태 갱신 + Redis pub/sub 알림
"""
import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

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
from app.topic.domain.models.topic import SimilarChunk, TopicDigest
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


_INCREMENTAL_SYSTEM_PROMPT = """You are a concise personal productivity assistant.
You are updating an existing markdown digest about a user's topic.
You are given the existing digest, NEW excerpts from journal entries written or edited
since it was generated, and the CURRENT list of related todos.

Requirements:
- Return the complete updated digest, not only the changes.
- Keep every fact from the existing digest that is still true.
- When the new content updates or supersedes an existing statement (e.g. a plan that is
  now done, a value that changed), rewrite that statement in place. Never keep both the
  old and the new version side by side.
- Integrate the new information into the appropriate sections; add a section only when
  nothing existing fits.
- Reflect the current todo statuses inside the relevant sections; do not add a separate
  todo list section.
- Do not grow the digest beyond what the new content genuinely adds; merge duplicates and
  keep the same level of detail as the existing digest.
- Use markdown headings, bullet points, and concise prose.
- Write in the same language as the source content.
- Do not invent information not present in the provided content.
"""

# 프롬프트를 바꾸면 올린다 — fingerprint 에 섞여 기존 digest 가 전체 재생성된다.
_PROMPT_VERSION = "3"


def _fingerprint(name: str, description: str | None, model: str, cfg: TopicConfig) -> str:
    """이 값이 바뀌면 이전 본문은 다른 기준으로 만든 것이라 증분으로 이어 쓸 수 없다."""
    raw = "|".join(
        [
            name,
            description or "",
            _PROMPT_VERSION,
            model,
            str(cfg.topic_similarity_threshold),
            str(cfg.topic_search_limit),
            str(cfg.topic_digest_neighbor_window),
        ]
    )
    return hashlib.sha1(raw.encode()).hexdigest()


def _static_full_reason(digest: TopicDigest, fingerprint: str, full_regen_every: int) -> str | None:
    """DB 조회 없이 판정 가능한 전체 재생성 사유. None 이면 증분 후보."""
    if digest.content is None or digest.last_generated_at is None:
        return "initial"
    if digest.full_fingerprint != fingerprint:
        return "fingerprint_changed"
    if digest.incremental_count >= full_regen_every:
        return "periodic_reset"
    return None


async def _with_neighbors(
    chunk_repo: EntryChunkRepository, user_id: str, chunks: list[SimilarChunk], window: int
) -> list[SimilarChunk]:
    """매칭 청크에 같은 회고의 앞뒤 청크를 붙인다 — 매칭 단락만 넣으면 맥락이 잘린다."""
    if window <= 0 or not chunks:
        return chunks
    have = {(c.entry_id, c.chunk_index) for c in chunks}
    wanted = {
        (c.entry_id, c.chunk_index + d)
        for c in chunks
        for d in range(-window, window + 1)
        if d != 0 and c.chunk_index + d >= 0
    } - have
    if not wanted:
        return chunks
    return chunks + await chunk_repo.find_by_entry_indices(user_id, sorted(wanted))


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
    previous_content: str | None = None,
) -> str:
    """프롬프트를 조립하며, 소스 하나를 접어 넣을 때마다 on_source(누적 처리 수)를 호출한다.

    `previous_content` 가 있으면 증분 — 기존 본문에 새 소스를 병합하도록 지시한다.
    """
    incremental = previous_content is not None
    system_prompt = _INCREMENTAL_SYSTEM_PROMPT if incremental else _SYSTEM_PROMPT
    lines = [system_prompt, "", f"## Topic: {topic_name}"]
    if topic_description:
        lines.append(f"Description: {topic_description}")
    if previous_content is not None:
        lines += ["", "### Existing Digest", previous_content]

    processed = 0

    if chunks:
        # 매칭 청크와 앞뒤 문맥 청크가 겹칠 수 있다 — 같은 단락을 두 번 싣지 않는다.
        unique: dict[tuple[str, int], Any] = {}
        for chunk in chunks:
            unique.setdefault((chunk.entry_id, chunk.chunk_index), chunk)
        chunks = list(unique.values())
        heading = "### New Journal Entry Excerpts" if incremental else "### Journal Entry Excerpts"
        lines += ["", heading]
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

    instruction = (
        "Return the complete updated markdown digest for this topic."
        if incremental
        else "Generate a markdown digest for this topic based on the above content."
    )
    lines += ["", "---", "", instruction]
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
    # ai.usage 로그의 사용자 귀속 — generate_summary 와 같은 이유로 태스크 밖으로 새지 않는다.
    structlog.contextvars.bind_contextvars(user_id=user_id)
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

                fingerprint = _fingerprint(
                    topic.name, topic.description, settings.ai.gemini_model, cfg
                )
                # 검색 "전"에 찍는다 — LLM 호출 중 임베딩된 청크가 다음 증분에서 빠지지 않게.
                # (이번 검색과 겹쳐 한 번 더 읽히는 쪽이 영영 빠지는 쪽보다 낫다)
                generated_at = datetime.now(timezone.utc)

                full_reason = _static_full_reason(
                    digest, fingerprint, cfg.topic_digest_full_regen_every
                )
                cursor = digest.last_generated_at
                new_chunks: list[SimilarChunk] = []
                if full_reason is None and cursor is not None:
                    # 이미 본문에 반영된 회고가 수정·삭제됐으면 증분으로는 되돌릴 수 없다.
                    if await chunk_repo.find_changed_entry_ids(
                        user_id, digest.source_entry_ids, cursor
                    ):
                        full_reason = "sources_changed"
                if full_reason is None:
                    new_chunks = await chunk_repo.search_similar(
                        user_id=user_id,
                        query_embedding=query_embedding,
                        since_date_key=None,
                        threshold=cfg.topic_similarity_threshold,
                        limit=cfg.topic_search_limit,
                        created_after=cursor,
                    )
                    # 새 소스 없이 생성을 요청했다 = 현재 결과가 마음에 안 든다는 신호.
                    if not new_chunks:
                        full_reason = "no_new_sources"

                # 증분 후보여도 전체 검색은 한다 — 아래에서 어느 쪽이 더 싼지 비교해야 한다.
                all_chunks = await _with_neighbors(
                    chunk_repo,
                    user_id,
                    await chunk_repo.search_similar(
                        user_id=user_id,
                        query_embedding=query_embedding,
                        since_date_key=None,
                        threshold=cfg.topic_similarity_threshold,
                        limit=cfg.topic_search_limit,
                    ),
                    cfg.topic_digest_neighbor_window,
                )
                # 할일은 상태 변경을 추적할 시각이 없고 한 줄씩이라 증분이어도 전부 싣는다.
                todos = await todo_emb_repo.search_similar(
                    user_id=user_id,
                    query_embedding=query_embedding,
                    since_date_key=None,
                    threshold=cfg.topic_similarity_threshold,
                    limit=cfg.topic_search_limit,
                )

                if full_reason is None:
                    new_chunks = await _with_neighbors(
                        chunk_repo, user_id, new_chunks, cfg.topic_digest_neighbor_window
                    )
                    # 증분은 직전 본문을 통째로 싣기 때문에, 소스가 적은 주제에선 원문 전체보다
                    # 오히려 길다(실측: 회고 12건 주제에서 전체 대비 119~131%). 더 짧을 때만 증분.
                    incremental_len = len(
                        await _build_prompt(
                            topic.name,
                            topic.description,
                            new_chunks,
                            todos,
                            previous_content=digest.content,
                        )
                    )
                    full_len = len(
                        await _build_prompt(topic.name, topic.description, all_chunks, todos)
                    )
                    if full_len <= incremental_len:
                        full_reason = "full_cheaper"

                incremental = full_reason is None
                chunks = new_chunks if incremental else all_chunks
                _log.info(
                    "generate_digest.mode",
                    digest_id=digest_id,
                    mode="incremental" if incremental else "full",
                    reason=full_reason,
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
                topic.name,
                topic.description,
                chunks,
                todos,
                on_source=publish_progress,
                previous_content=digest.content if incremental else None,
            )

            # AI 호출 — DB transaction 밖
            from app.topic.infrastructure.ai.gemini_client import TopicGeminiClient
            gemini = TopicGeminiClient(settings.ai)
            content = await gemini.generate(prompt)

            # T2: complete. watermark_date_key 는 "이 문서가 언제 기준인가"(FE 배너/미반영 개수
            # 기준점)이고, 증분 커서는 시각인 last_generated_at 이 따로 맡는다.
            new_entry_ids = list(dict.fromkeys(c.entry_id for c in chunks))
            if incremental:
                source_entry_ids = list(dict.fromkeys(digest.source_entry_ids + new_entry_ids))
                incremental_count = digest.incremental_count + 1
            else:
                source_entry_ids = new_entry_ids
                incremental_count = 0
            async with factory.begin() as session:
                await TopicDigestRepository(session).complete_generation(
                    digest_id,
                    content=content,
                    watermark_date_key=today_key,
                    generated_at=generated_at,
                    incremental_count=incremental_count,
                    full_fingerprint=fingerprint,
                    source_entry_ids=source_entry_ids,
                )

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
