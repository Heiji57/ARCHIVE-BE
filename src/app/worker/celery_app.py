import os
from datetime import timedelta

from celery import Celery, signals
from celery.schedules import crontab
from kombu import Exchange, Queue

from app.shared.infrastructure.config.settings import get_settings
from app.shared.infrastructure.logger.setup import configure_logging

# Google Calendar 백그라운드 동기화 주기(분). 기본 5분.
_CALENDAR_SYNC_INTERVAL_MINUTES = int(os.getenv("CALENDAR_SYNC_INTERVAL_MINUTES", "5"))

_QUEUES = (
    Queue("ai_tasks", Exchange("ai_tasks"), routing_key="ai_tasks", max_priority=9),
    Queue("default", Exchange("default"), routing_key="default"),
    # 캘린더 백그라운드 동기화 전용 — 시간에 민감한 요약 dispatcher(default)와
    # 무거운 AI 요약(ai_tasks) 양쪽에서 격리.
    Queue("calendar", Exchange("calendar"), routing_key="calendar"),
)

_TASK_ROUTES = {
    "worker.generate_summary": {"queue": "ai_tasks"},
    "worker.generate_digest": {"queue": "ai_tasks"},
    "worker.dispatch_summaries_for_tz": {"queue": "default"},
    "worker.embed_stale": {"queue": "default"},
    "worker.sync_all_calendars": {"queue": "calendar"},
    "worker.sync_user_calendar": {"queue": "calendar"},
    # ARCHIVE → Google push — calendar 큐에서 격리 처리(즉시 단건 + 삭제 cleanup).
    "worker.push_calendar_event": {"queue": "calendar"},
    "worker.delete_calendar_event": {"queue": "calendar"},
}


@signals.setup_logging.connect
def _configure_worker_logging(**_: object) -> None:
    # 이 시그널에 수신자가 있으면 Celery 는 루트 로거를 가로채지 않는다 — API 와 같은 JSON
    # 포맷으로 남고, 태스크 로그에는 AsyncContextTask 가 바인딩한 task_id/task_name 이 붙는다.
    configure_logging()


def create_celery_app() -> Celery:
    settings = get_settings()
    # AsyncContextTask — celery_aio_pool 루프 스레드에서 self.request(retry·retries)를 복원한다.
    app = Celery("archive", task_cls="app.worker.task_base:AsyncContextTask")
    app.conf.update(
        broker_url=settings.redis.broker_url,
        result_backend=settings.redis.result_backend_url,
        worker_pool="celery_aio_pool.pool.AsyncIOPool",
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_queues=_QUEUES,
        task_routes=_TASK_ROUTES,
        task_default_queue="default",
        # 매시간 정각 dispatcher 발사. dispatcher가 각 사용자의 tz 기준 "현지 1am" 여부를
        # 판단해 fan-out한다. UTC 단일 beat이지만 사용자별로 다른 tz 처리 가능.
        beat_schedule={
            "dispatch-summaries-hourly": {
                "task": "worker.dispatch_summaries_for_tz",
                "schedule": crontab(minute=0),  # 매시간 정각
            },
            # 활성 사용자 캘린더를 N분마다 백그라운드 동기화 (기본 5분).
            "sync-calendars-periodic": {
                "task": "worker.sync_all_calendars",
                "schedule": timedelta(minutes=_CALENDAR_SYNC_INTERVAL_MINUTES),
            },
            # embedding_queue 드레이너 — 5분마다 stale 항목 처리.
            "embed-stale-periodic": {
                "task": "worker.embed_stale",
                "schedule": timedelta(minutes=5),
            },
        },
    )
    app.autodiscover_tasks([
        "app.worker.tasks.generate_summary",
        "app.worker.tasks.dispatch_summaries_for_tz",
        "app.worker.tasks.sync_calendars",
        "app.worker.tasks.push_calendars",
        "app.worker.tasks.embed_stale",
        "app.worker.tasks.generate_digest",
    ])
    return app


celery_app = create_celery_app()
