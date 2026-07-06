"""Google Calendar 백그라운드 주기 동기화.

`GET /todos` 의 온디맨드 sync 는 사용자가 앱을 열 때만, 그것도 staleness 창
안에서는 Google 을 다시 보지 않는다. 그래서 구글 캘린더에 새 일정을 추가해도
즉시 반영되지 않아 수동 동기화 버튼을 눌러야 했다.

이 태스크가 Celery beat 으로 N분마다 발사돼 **최근 활성 사용자**(요청 경로에서
`last_active_at` 이 갱신된 사용자)의 캘린더만 증분 동기화한다. 덕분에:
- 수동 버튼 없이 서버가 알아서 최신 상태 유지.
- `GET /todos` 는 DB 만 읽어 빠름(요청 경로 Google 호출 최소화).
- 비활성 사용자는 polling 하지 않아 API 쿼터 낭비 없음.

dispatcher(`sync_all_calendars`)가 활성 사용자를 모아 사용자별 결정적 지터로
per-user 태스크(`sync_user_calendar`)를 fan-out 한다 — 정각 버스트를 분산하고
한 사용자의 실패가 다른 사용자에 영향을 주지 않게 격리한다.
"""
import hashlib
import os
from datetime import datetime, timedelta, timezone

import structlog
from redis.asyncio import Redis

from app.google_calendar.application.use_cases.sync_calendar_events import (
    SyncCalendarEventsUseCase,
)
from app.google_calendar.infrastructure.api.google_calendar_client import (
    GoogleCalendarApiClient,
)
from app.worker.tasks.push_calendars import run_batch_push
from app.google_calendar.infrastructure.persistence.repositories.calendar_connection_repo import (
    GoogleCalendarConnectionRepository,
)
from app.google_calendar.infrastructure.persistence.repositories.calendar_event_repo import (
    CalendarEventRepository,
)
from app.settings.infrastructure.persistence.repositories.user_settings_repo import (
    UserSettingsRepository,
)
from app.shared.infrastructure.config.settings import get_settings
from app.todo.infrastructure.persistence.repositories.todo_repo import TodoRepository
from app.worker.celery_app import celery_app
from app.worker.db import get_worker_session_factory

_log = structlog.get_logger(__name__)

# 최근 이 일수 안에 캘린더를 조회한 사용자만 백그라운드 sync 대상.
CALENDAR_ACTIVE_DAYS = int(os.getenv("CALENDAR_ACTIVE_DAYS", "7"))
# per-user sync 를 0 ~ 이 초 사이로 분산(정각 버스트 완화). 5분 창 안에 들도록 < 300.
CALENDAR_SYNC_JITTER_SECONDS = int(os.getenv("CALENDAR_SYNC_JITTER_SECONDS", "240"))


def _user_jitter_seconds(user_id: str) -> int:
    """사용자별 결정적 지터 — 같은 사용자는 항상 같은 초 만큼 지연."""
    if CALENDAR_SYNC_JITTER_SECONDS <= 0:
        return 0
    digest = hashlib.sha256(user_id.encode()).hexdigest()
    return int(digest, 16) % CALENDAR_SYNC_JITTER_SECONDS


@celery_app.task(name="worker.sync_all_calendars")
async def sync_all_calendars_task() -> None:
    """활성 사용자 캘린더 동기화 dispatcher — beat 으로 N분마다 발사."""
    factory = get_worker_session_factory()
    active_since = datetime.now(timezone.utc) - timedelta(days=CALENDAR_ACTIVE_DAYS)

    async with factory.begin() as session:
        connection_repo = GoogleCalendarConnectionRepository(session)
        user_ids = await connection_repo.find_active_user_ids(active_since)

    for user_id in user_ids:
        sync_user_calendar_task.si(user_id).apply_async(
            countdown=_user_jitter_seconds(user_id), queue="calendar"
        )

    _log.info("calendar.sync_all.dispatched", count=len(user_ids))


@celery_app.task(
    name="worker.sync_user_calendar",
    # 일시 장애는 use case 내부에서 흡수(연결 보존)하므로 task 자동 재시도는 두지 않는다.
    rate_limit="120/m",
)
async def sync_user_calendar_task(user_id: str) -> None:
    """단일 사용자 캘린더 증분 동기화(force=True). 실패는 로깅 후 skip — 격리."""
    settings = get_settings()
    factory = get_worker_session_factory()
    api_client = GoogleCalendarApiClient(settings.google_calendar)
    redis = Redis.from_url(settings.redis.cache_url, decode_responses=True)
    try:
        # 1) Google → ARCHIVE 증분 pull-sync (기존).
        async with factory.begin() as session:
            use_case = SyncCalendarEventsUseCase(
                connection_repo=GoogleCalendarConnectionRepository(session),
                event_repo=CalendarEventRepository(session),
                api_client=api_client,
                config=settings.google_calendar,
                todo_repo=TodoRepository(session),
                settings_repo=UserSettingsRepository(session),
            )
            await use_case.execute(user_id, force=True)
        # 2) ARCHIVE → Google push (pending/failed/stuck 배치 처리). pull-sync 뒤 실행 —
        #    같은 calendar 큐 워커에서 배치 처리해 시간에 민감한 요약/AI 큐와 격리.
        await run_batch_push(factory, api_client, settings.google_calendar, user_id, redis)
    except Exception:
        _log.warning("calendar.sync_user.failed", user_id=user_id, exc_info=True)
    finally:
        await api_client.close()
        await redis.aclose()
