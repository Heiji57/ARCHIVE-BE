"""ARCHIVE todo → Google Calendar push (양방향 동기화의 push 절반).

트랜잭션 안무(claim / heartbeat / finalize)를 이 워커가 소유하고, per-todo Google
API 로직은 `CalendarPushService` 에 위임한다. 3단계 구조:

  1. claim txn      : SKIP LOCKED 로 처리 대상을 'syncing' 원자 마킹(동시 워커 중복 방지)
  2. HTTP (no txn)  : 각 todo 처리 직전 heartbeat 로 소유권 갱신 후 Google 호출
  3. finalize txn   : sync_attempt_id 가드로 결과 반영(사용자 편집/재claim 과의 lost-update 방지)

claim 과 finalize 를 짧은 개별 트랜잭션으로 분리해 Google HTTP 호출 동안 DB 락을
잡지 않는다. finalize 가 race 로 0행이면(상태 변경됨) 이번에 새로 만든 이벤트만
orphan 정리한다.
"""
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.google_calendar.application.services.calendar_push_service import (
    CalendarPushService,
    PushOutcome,
)
from app.google_calendar.application.services.token_manager import (
    ensure_valid_access_token,
)
from app.google_calendar.domain.exceptions.exceptions import (
    CalendarApiUnavailableException,
    CalendarReauthRequiredException,
)
from app.google_calendar.infrastructure.api.google_calendar_client import (
    GoogleCalendarApiClient,
)
from app.google_calendar.infrastructure.persistence.repositories.calendar_connection_repo import (
    GoogleCalendarConnectionRepository,
)
from app.shared.domain.utils.id import generate_id
from app.shared.infrastructure.config.oauth import GoogleCalendarConfig
from app.shared.infrastructure.config.settings import get_settings
from app.todo.domain.models.todo import Todo
from app.todo.infrastructure.persistence.repositories.todo_repo import TodoRepository
from app.worker.celery_app import celery_app
from app.worker.db import get_worker_session_factory

_log = structlog.get_logger(__name__)


async def _publish_todo_sync_event(
    redis: Redis,
    user_id: str,
    todo_id: str,
    calendar_linked: bool,
    calendar_push_status: str | None,
    type_: str,
) -> None:
    """캘린더 push 완료(성공/실패/연동해제)를 ephemeral SSE 이벤트로 알림.

    DB 에 저장하지 않는다 — `notifications:{user_id}` 채널에 실려가는 순간만
    존재하는 신호이며, FE 는 `resource=="todo"` 로 구분해 알림 패널에 쌓지 않고
    todo 상태 갱신에만 쓴다. publish 실패가 실제 push 결과(DB 확정)를 막으면
    안 되므로 best-effort 로 삼킨다.
    """
    payload = {
        "id": generate_id("notf"),
        "type": type_,
        "category": "sync",
        "resource": "todo",
        "todo_id": todo_id,
        "calendar_linked": calendar_linked,
        "calendar_push_status": calendar_push_status,
        "title": "",
        "message": "",
        "is_read": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await redis.publish(f"notifications:{user_id}", json.dumps(payload))
    except Exception:
        _log.warning(
            "calendar.push.sse_publish_failed",
            user_id=user_id,
            todo_id=todo_id,
            exc_info=True,
        )


async def _acquire_access_token(
    factory: async_sessionmaker[AsyncSession],
    api_client: GoogleCalendarApiClient,
    user_id: str,
    now: datetime,
) -> str | None:
    """연결 조회 + 토큰 확보(한 번). 미연결/needs_reauth 면 None(사이클 스킵)."""
    async with factory.begin() as session:
        conn_repo = GoogleCalendarConnectionRepository(session)
        conn = await conn_repo.find_by_user_id(user_id)
        if conn is None:
            return None
        return await ensure_valid_access_token(conn, api_client, conn_repo, now)


async def _mark_needs_reauth(
    factory: async_sessionmaker[AsyncSession], user_id: str
) -> None:
    """push 사이클 중 401(revoke) → 재연결 유도. 남은 syncing 행은 이후 stuck recovery."""
    async with factory.begin() as session:
        conn_repo = GoogleCalendarConnectionRepository(session)
        conn = await conn_repo.find_by_user_id(user_id)
        if conn is not None:
            conn.needs_reauth = True
            conn.updated_at = datetime.now(timezone.utc)
            await conn_repo.save(conn)


async def _finalize(
    factory: async_sessionmaker[AsyncSession],
    api_client: GoogleCalendarApiClient,
    redis: Redis,
    access_token: str,
    user_id: str,
    todo: Todo,
    attempt_id: str,
    outcome: PushOutcome,
) -> None:
    async with factory.begin() as session:
        repo = TodoRepository(session)
        if outcome.kind == "delete_success":
            affected = await repo.finalize_delete_success(todo.id, user_id, attempt_id)
        else:  # push_success
            assert outcome.result_gid is not None
            affected = await repo.finalize_push_success(
                todo.id, user_id, attempt_id, outcome.result_gid
            )
    # finalize race(상태 변경됨) + 이번에 새로 만든 이벤트 → orphan(중복) 정리.
    if (
        not affected
        and outcome.kind == "push_success"
        and outcome.newly_created
        and outcome.result_gid
    ):
        try:
            await api_client.delete_event(access_token, outcome.result_gid)
        except Exception:
            _log.warning(
                "calendar.push.orphan_cleanup_failed",
                user_id=user_id,
                gid=outcome.result_gid,
                exc_info=True,
            )
    if affected:
        if outcome.kind == "delete_success":
            await _publish_todo_sync_event(
                redis, user_id, todo.id, calendar_linked=False,
                calendar_push_status=None, type_="success",
            )
        else:  # push_success
            await _publish_todo_sync_event(
                redis, user_id, todo.id, calendar_linked=True,
                calendar_push_status="synced", type_="success",
            )


async def _finalize_failure(
    factory: async_sessionmaker[AsyncSession],
    redis: Redis,
    user_id: str,
    todo: Todo,
    attempt_id: str,
) -> None:
    async with factory.begin() as session:
        repo = TodoRepository(session)
        affected = await repo.finalize_push_failure(
            todo.id, user_id, attempt_id, todo.push_retry_count + 1
        )
    if affected:
        await _publish_todo_sync_event(
            redis, user_id, todo.id, calendar_linked=False,
            calendar_push_status="failed", type_="warning",
        )


async def _process_claimed(
    factory: async_sessionmaker[AsyncSession],
    api_client: GoogleCalendarApiClient,
    redis: Redis,
    user_id: str,
    claimed: list[Todo],
    access_token: str,
) -> None:
    """claim 된 todo 들을 순차 처리. reauth 는 상위로 전파(사이클 중단)."""
    push_service = CalendarPushService(api_client)
    for todo in claimed:
        attempt_id = todo.sync_attempt_id
        if attempt_id is None:
            continue  # 방어적 — claim 결과라면 항상 세팅돼 있음

        # 처리 직전 heartbeat — 배치 내 큐잉 지연이 stuck 으로 오탐돼 재claim 되는 것 방지.
        # 0행이면 이미 소유권 상실(재claim 당함) → 이 항목 건너뜀(중복 처리 방지).
        async with factory.begin() as session:
            repo = TodoRepository(session)
            if not await repo.heartbeat_push(todo.id, user_id, attempt_id):
                continue

        try:
            outcome = await push_service.push_one(access_token, todo)
        except CalendarReauthRequiredException:
            raise  # 사이클 중단 — 남은 항목은 이후 재claim
        except CalendarApiUnavailableException:
            await _finalize_failure(factory, redis, user_id, todo, attempt_id)
            continue
        except Exception:
            _log.warning(
                "calendar.push.unexpected",
                user_id=user_id,
                todo_id=todo.id,
                exc_info=True,
            )
            await _finalize_failure(factory, redis, user_id, todo, attempt_id)
            continue

        await _finalize(
            factory, api_client, redis, access_token, user_id, todo, attempt_id, outcome
        )


async def run_batch_push(
    factory: async_sessionmaker[AsyncSession],
    api_client: GoogleCalendarApiClient,
    config: GoogleCalendarConfig,
    user_id: str,
    redis: Redis,
) -> None:
    """사용자의 pending/failed/stuck push 를 배치 처리. sync_user_calendar_task 가 호출."""
    now = datetime.now(timezone.utc)
    access_token = await _acquire_access_token(factory, api_client, user_id, now)
    if access_token is None:
        return

    attempt_id = uuid4().hex
    async with factory.begin() as session:
        repo = TodoRepository(session)
        claimed = await repo.claim_pending_pushes(
            user_id,
            attempt_id,
            max_retries=config.calendar_push_max_retries,
            stuck_before=now - timedelta(seconds=config.calendar_push_stuck_seconds),
            batch_size=config.calendar_push_batch_size,
        )
    if not claimed:
        return

    try:
        await _process_claimed(factory, api_client, redis, user_id, claimed, access_token)
    except CalendarReauthRequiredException:
        _log.warning("calendar.push.reauth_mid_cycle", user_id=user_id)
        await _mark_needs_reauth(factory, user_id)


@celery_app.task(name="worker.push_calendar_event", rate_limit="240/m")
async def push_calendar_event_task(user_id: str, todo_id: str) -> None:
    """즉시 단건 push — 라우터가 todo 생성/수정/연동해제 직후 enqueue.

    배치 주기(수 분)를 기다리지 않고 곧바로 반영. 배치와 동일한 claim/heartbeat/
    finalize 루틴을 공유하며, 이미 배치가 가져간 경우(claim 0행)엔 no-op.
    """
    settings = get_settings()
    factory = get_worker_session_factory()
    api_client = GoogleCalendarApiClient(settings.google_calendar)
    redis = Redis.from_url(settings.redis.cache_url, decode_responses=True)
    try:
        now = datetime.now(timezone.utc)
        access_token = await _acquire_access_token(factory, api_client, user_id, now)
        if access_token is None:
            return

        attempt_id = uuid4().hex
        async with factory.begin() as session:
            repo = TodoRepository(session)
            claimed = await repo.claim_single_pending_push(todo_id, user_id, attempt_id)
        if claimed is None:
            return

        try:
            await _process_claimed(factory, api_client, redis, user_id, [claimed], access_token)
        except CalendarReauthRequiredException:
            await _mark_needs_reauth(factory, user_id)
    except Exception:
        _log.warning(
            "calendar.push_immediate.failed",
            user_id=user_id,
            todo_id=todo_id,
            exc_info=True,
        )
    finally:
        await api_client.close()
        await redis.aclose()


@celery_app.task(
    name="worker.delete_calendar_event",
    autoretry_for=(CalendarApiUnavailableException,),
    retry_backoff=True,
    max_retries=5,
)
async def delete_calendar_event_task(user_id: str, google_event_id: str) -> None:
    """best-effort Google 이벤트 삭제 — 전체 todo 삭제(DELETE /todos/{id}) 시 enqueue.

    todo 행은 이미 삭제됐으므로 push 상태 추적 없이 fire-and-forget. 일시 장애는
    autoretry, 404 는 멱등 성공. 재시도 소진 시 orphan 은 수용(경고 로깅).
    """
    settings = get_settings()
    factory = get_worker_session_factory()
    api_client = GoogleCalendarApiClient(settings.google_calendar)
    try:
        now = datetime.now(timezone.utc)
        access_token = await _acquire_access_token(factory, api_client, user_id, now)
        if access_token is None:
            return
        try:
            await api_client.delete_event(access_token, google_event_id)
        except CalendarReauthRequiredException:
            # 재연결 필요 상태 — 삭제 불가. best-effort 이므로 orphan 수용.
            _log.warning(
                "calendar.delete_event.reauth_required",
                user_id=user_id,
                gid=google_event_id,
            )
    finally:
        await api_client.close()
