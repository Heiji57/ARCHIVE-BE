from celery import Celery
from celery.schedules import crontab

from app.shared.infrastructure.config.settings import get_settings


def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery("archive")
    app.conf.update(
        broker_url=settings.redis.broker_url,
        result_backend=settings.redis.result_backend_url,
        worker_pool="celery_aio_pool.pool.AsyncPool",
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        beat_schedule={
            "schedule-summaries-daily": {
                "task": "worker.schedule_summaries",
                "schedule": crontab(hour=1, minute=0),
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
