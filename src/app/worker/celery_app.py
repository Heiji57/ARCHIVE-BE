from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue

from app.shared.infrastructure.config.settings import get_settings

_QUEUES = (
    Queue("ai_tasks", Exchange("ai_tasks"), routing_key="ai_tasks", max_priority=9),
    Queue("default", Exchange("default"), routing_key="default"),
)

_TASK_ROUTES = {
    "worker.generate_summary": {"queue": "ai_tasks"},
    "worker.dispatch_summaries_for_tz": {"queue": "default"},
}


def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery("archive")
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
        },
    )
    app.autodiscover_tasks([
        "app.worker.tasks.generate_summary",
        "app.worker.tasks.dispatch_summaries_for_tz",
    ])
    return app


celery_app = create_celery_app()
