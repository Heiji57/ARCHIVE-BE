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
    "worker.generate_from_child_summaries": {"queue": "ai_tasks"},
    "worker.schedule_summaries": {"queue": "default"},
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
        beat_schedule={
            "schedule-annual-summaries": {
                "task": "worker.schedule_summaries",
                "schedule": crontab(hour=1, minute=0, month_of_year=1, day_of_month=1),
                "args": ["annual"],
            },
            "schedule-monthly-summaries": {
                "task": "worker.schedule_summaries",
                "schedule": crontab(hour=1, minute=0, day_of_month=1),
                "args": ["monthly"],
            },
            "schedule-weekly-summaries": {
                "task": "worker.schedule_summaries",
                "schedule": crontab(hour=1, minute=0, day_of_week=1),
                "args": ["weekly"],
            },
        },
    )
    app.autodiscover_tasks([
        "app.worker.tasks.generate_summary",
        "app.worker.tasks.generate_from_child_summaries",
        "app.worker.tasks.schedule_summaries",
    ])
    return app


celery_app = create_celery_app()
