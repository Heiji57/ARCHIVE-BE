"""토픽 다이제스트 생성 Celery task.

흐름:
  1. mark in_progress
  2. 사용자의 embedding_queue 잔여 항목 사전 동기화
  3. 토픽 쿼리 벡터 생성
  4. 전체/증분 판정 후 entry chunk(+앞뒤 청크) / todo embedding 유사도 검색
  5. 프롬프트 조립 — 근거마다 짧은 표식(E1, T1)을 붙여 싣고, 진행률 pub/sub 발행
  6. Gemini 로 구조화 정리(JSON) 생성 → 표식을 실제 id 로 바꾸고 검증(한 번 재요청)
  7. mark completed(구조 + 구조에서 만든 markdown) + watermark·증분 상태 갱신 + 알림
"""
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
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
from app.topic.domain.models.structured_digest import (
    MAX_ITEM_TEXT,
    MAX_ITEMS_PER_THEME,
    MAX_SUMMARY,
    MAX_THEME_NAME,
    MAX_THEMES,
    SourceRef,
    StructuredDigest,
    normalize,
)
from app.topic.domain.models.topic import SimilarChunk, TopicDigest
from app.topic.domain.models.value_objects import DigestStatus
from app.topic.infrastructure.ai.embedding_service import EmbeddingService
from app.topic.infrastructure.persistence.repositories.chunk_repo import (
    EmbeddingQueueRepository,
    EntryChunkRepository,
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

_OUTPUT_RULES = f"""Output: JSON only, matching the response schema.
- "summary": one sentence (max {MAX_SUMMARY} chars) on where the user stands on this topic now.
- "themes": the larger sub-themes of the work, 2 to {MAX_THEMES} (a single theme is fine when
  there are 3 or fewer sources). Each theme has a short "name" (max {MAX_THEME_NAME} chars),
  a one-sentence "summary" (max {MAX_SUMMARY} chars) and "items".
- "items": what the user actually did, one per source per theme (max {MAX_ITEMS_PER_THEME} per
  theme). "source" is the label of the source it comes from (e.g. "E3", "T5") — use only labels
  given below, never invent one. "text" (max {MAX_ITEM_TEXT} chars) states the concrete thing done.
- The same source may appear under several themes when it really belongs to both.
- Do not output dates; the server takes each item's date from its source.
- Write in the same language as the source content.
- Do not invent information not present in the provided content.
"""

_SYSTEM_PROMPT = f"""You are a concise personal productivity assistant.
Given a user's topic and labeled excerpts from their journal entries ([E…]) and todos ([T…]),
organize what they have been doing on this topic into themes and dated items.

{_OUTPUT_RULES}"""


_INCREMENTAL_SYSTEM_PROMPT = f"""You are a concise personal productivity assistant.
You are updating an existing structured digest about a user's topic.
You are given the existing digest (JSON, sources as labels), NEW labeled excerpts from journal
entries written or edited since it was generated, and the CURRENT list of related todos.

Update rules:
- Return the complete updated digest, not only the changes.
- Keep the existing theme names and their order. Put each new source into the theme it fits;
  create a new theme only when nothing existing fits.
- Keep every existing item that is still true. When new content updates or supersedes an item
  (e.g. a plan that is now done), rewrite that item in place — never keep both versions.
- Reflect the current todo statuses in the items.
- Rewrite the overall "summary" so it reflects the latest state.

{_OUTPUT_RULES}"""

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "themes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "summary": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "string"},
                                "text": {"type": "string"},
                            },
                            "required": ["source", "text"],
                        },
                    },
                },
                "required": ["name", "summary", "items"],
            },
        },
    },
    "required": ["summary", "themes"],
}

# 모델 출력이 JSON 이 아니거나 근거를 하나도 가리키지 못하면 한 번 더 묻는다.
_MAX_STRUCTURE_ATTEMPTS = 2

# 프롬프트를 바꾸면 올린다 — fingerprint 에 섞여 기존 digest 가 전체 재생성된다.
_PROMPT_VERSION = "4"


class DigestInvalidOutputError(Exception):
    """모델 출력이 두 번 모두 구조 검증에 실패 — 정리 실패(DIGEST_INVALID_OUTPUT)."""

    code = "DIGEST_INVALID_OUTPUT"


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
    if digest.structured is None:
        # 구조화 도입 전 markdown 정리 — 이어 쓸 구조가 없다.
        return "unstructured"
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


@dataclass(frozen=True)
class SourceLabels:
    """프롬프트의 근거 표식 ↔ 실제 대상. 모델은 표식으로만 근거를 가리킨다."""

    by_label: dict[str, SourceRef]
    entry_label: dict[str, str]  # entry_id -> "E1"
    todo_label: dict[str, str]  # todo_id -> "T1"


def _label_sources(
    chunks: list[Any], todos: list[Any], previous: StructuredDigest | None = None
) -> SourceLabels:
    """회고는 E1.., 할 일은 T1.. — 프롬프트에 싣는 순서대로, 이어서 직전 정리에만 있는 근거."""
    by_label: dict[str, SourceRef] = {}
    entry_label: dict[str, str] = {}
    todo_label: dict[str, str] = {}

    def add_entry(entry_id: str, date_key: str) -> None:
        if entry_id not in entry_label:
            label = f"E{len(entry_label) + 1}"
            entry_label[entry_id] = label
            by_label[label] = SourceRef("entry", entry_id, date_key)

    def add_todo(todo_id: str, date_key: str) -> None:
        if todo_id not in todo_label:
            label = f"T{len(todo_label) + 1}"
            todo_label[todo_id] = label
            by_label[label] = SourceRef("todo", todo_id, date_key)

    for c in _ordered_chunks(chunks):
        add_entry(c.entry_id, c.date_key)
    for t in todos:
        add_todo(t.todo_id, t.date_key)
    if previous is not None:
        for theme in previous.themes:
            for item in theme.items:
                if item.source_kind == "entry":
                    add_entry(item.source_id, item.date_key)
                else:
                    add_todo(item.source_id, item.date_key)
    return SourceLabels(by_label, entry_label, todo_label)


def _ordered_chunks(chunks: list[Any]) -> list[Any]:
    """중복 제거 후, 회고 등장 순서(가장 유사한 청크 기준)를 지키며 회고 안에서는 chunk_index 순.

    chunks 는 유사도(코사인 거리) 순으로 오고 entry_id 로 묶여 있지 않다 — 그대로 훑으면
    한 회고의 뒤늦은 청크가 다른 회고 밑에 잘못 붙는다. 매칭 청크와 앞뒤 문맥 청크가
    겹칠 수 있어 같은 단락을 두 번 싣지 않는다.
    """
    unique: dict[tuple[str, int], Any] = {}
    for chunk in chunks:
        unique.setdefault((chunk.entry_id, chunk.chunk_index), chunk)
    entry_order: dict[str, int] = {}
    for chunk in unique.values():
        entry_order.setdefault(chunk.entry_id, len(entry_order))
    return sorted(unique.values(), key=lambda c: (entry_order[c.entry_id], c.chunk_index))


def _previous_as_labeled_json(previous: StructuredDigest, labels: SourceLabels) -> str:
    """직전 구조를 표식으로 바꿔 싣는다 — 모델이 UUID 를 보지도 되돌려주지도 않게."""

    def label_of(kind: str, source_id: str) -> str:
        return (labels.entry_label if kind == "entry" else labels.todo_label)[source_id]

    return json.dumps(
        {
            "summary": previous.summary,
            "themes": [
                {
                    "name": t.name,
                    "summary": t.summary,
                    "items": [
                        {"source": label_of(i.source_kind, i.source_id), "text": i.text}
                        for i in t.items
                    ],
                }
                for t in previous.themes
            ],
        },
        ensure_ascii=False,
    )


async def _build_prompt(
    topic_name: str,
    topic_description: str,
    chunks: list[Any],
    todos: list[Any],
    on_source: Callable[[int], Awaitable[None]] | None = None,
    previous: StructuredDigest | None = None,
    labels: SourceLabels | None = None,
) -> str:
    """프롬프트를 조립하며, 소스 하나를 접어 넣을 때마다 on_source(누적 처리 수)를 호출한다.

    `previous` 가 있으면 증분 — 직전 구조에 새 소스를 병합하도록 지시한다.
    `labels` 는 응답을 되돌릴 때 같은 표식을 써야 하므로 호출자가 만들어 넘긴다.
    """
    incremental = previous is not None
    labels = labels or _label_sources(chunks, todos, previous)
    system_prompt = _INCREMENTAL_SYSTEM_PROMPT if incremental else _SYSTEM_PROMPT
    lines = [system_prompt, "", f"## Topic: {topic_name}"]
    if topic_description:
        lines.append(f"Description: {topic_description}")
    if previous is not None:
        lines += ["", "### Existing Digest", _previous_as_labeled_json(previous, labels)]

    processed = 0

    if chunks:
        heading = "### New Journal Entry Excerpts" if incremental else "### Journal Entry Excerpts"
        lines += ["", heading]
        seen: set[str] = set()
        for chunk in _ordered_chunks(chunks):
            if chunk.entry_id not in seen:
                seen.add(chunk.entry_id)
                lines.append(f"\n[{labels.entry_label[chunk.entry_id]}] {chunk.date_key}")
                processed += 1
                if on_source is not None:
                    await on_source(processed)
            lines.append(f"- {chunk.text}")

    if todos:
        lines += ["", "### Related Todos"]
        for todo in todos:
            label = labels.todo_label[todo.todo_id]
            lines.append(f"- [{label}] {todo.date_key} {todo.status} {todo.text}")
            processed += 1
            if on_source is not None:
                await on_source(processed)

    instruction = (
        "Return the complete updated digest as JSON."
        if incremental
        else "Generate the structured digest for this topic as JSON."
    )
    lines += ["", "---", "", instruction]
    return "\n".join(lines)


async def _generate_structured(
    gemini: Any, prompt: str, labels: SourceLabels, digest_id: str
) -> StructuredDigest:
    """JSON 생성 → 표식 치환·검증. 근거가 있는데 항목이 하나도 안 남으면 한 번 더 묻는다."""
    for attempt in range(1, _MAX_STRUCTURE_ATTEMPTS + 1):
        try:
            raw = await gemini.generate_json(prompt, _RESPONSE_SCHEMA)
        except ValueError:
            _log.warning("generate_digest.invalid_json", digest_id=digest_id, attempt=attempt)
            continue
        if not isinstance(raw, dict):
            _log.warning("generate_digest.invalid_shape", digest_id=digest_id, attempt=attempt)
            continue
        structured = normalize(raw, labels.by_label)
        if structured.themes or not labels.by_label:
            return structured
        _log.warning(
            "generate_digest.no_valid_items",
            digest_id=digest_id,
            attempt=attempt,
            raw_preview=json.dumps(raw, ensure_ascii=False)[:500],
        )
    raise DigestInvalidOutputError("Model output failed structure validation twice.")


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
                            previous=digest.structured,
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
            previous = digest.structured if incremental else None
            labels = _label_sources(chunks, todos, previous)
            prompt = await _build_prompt(
                topic.name,
                topic.description,
                chunks,
                todos,
                on_source=publish_progress,
                previous=previous,
                labels=labels,
            )

            # AI 호출 — DB transaction 밖
            from app.topic.infrastructure.ai.gemini_client import TopicGeminiClient
            gemini = TopicGeminiClient(settings.ai)
            structured = await _generate_structured(gemini, prompt, labels, digest_id)

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
                    content=structured.to_markdown(),
                    watermark_date_key=today_key,
                    generated_at=generated_at,
                    incremental_count=incremental_count,
                    full_fingerprint=fingerprint,
                    source_entry_ids=source_entry_ids,
                    structured=structured,
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
        _log.exception(
            "generate_digest.failed",
            digest_id=digest_id,
            error_code=getattr(exc, "code", type(exc).__name__),
        )
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
