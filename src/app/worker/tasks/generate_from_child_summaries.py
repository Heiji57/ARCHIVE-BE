import json

from redis.asyncio import Redis

from app.notification.domain.models.notification import Notification
from app.notification.domain.models.value_objects import NotificationCategory, NotificationType
from app.notification.infrastructure.persistence.repositories.notification_repo import NotificationRepository
from app.retrospective.domain.exceptions.exceptions import SummaryAlreadyInProgressException
from app.retrospective.domain.models.value_objects import SummaryType
from app.retrospective.infrastructure.ai.gemini_client import GeminiSummaryClient
from app.retrospective.infrastructure.ai.prompt_builder import build_prompt_from_summaries
from app.retrospective.infrastructure.persistence.repositories.retro_summary_repo import RetroSummaryRepository
from app.shared.infrastructure.config.settings import get_settings
from app.worker.celery_app import celery_app
from app.worker.db import get_worker_session_factory

_TYPE_KO = {
    SummaryType.WEEKLY: "주간",
    SummaryType.MONTHLY: "월간",
    SummaryType.ANNUAL: "연간",
}

_CHILD_SUMMARY_TYPE = {
    SummaryType.MONTHLY: SummaryType.WEEKLY,
    SummaryType.ANNUAL: SummaryType.MONTHLY,
}


@celery_app.task(name="worker.generate_from_child_summaries", rate_limit="60/m")
async def generate_from_child_summaries_task(
    summary_id: str, user_id: str, send_notification: bool = True
) -> None:
    settings = get_settings()
    factory = get_worker_session_factory()
    redis = Redis.from_url(settings.redis.cache_url, decode_responses=True)

    try:
        # ── Transaction 1: mark in_progress + fetch child summaries ──────────
        async with factory.begin() as session:
            summary_repo = RetroSummaryRepository(session)

            summary = await summary_repo.find_by_id(summary_id, user_id)
            if not summary:
                return

            try:
                summary.mark_in_progress()
            except SummaryAlreadyInProgressException:
                return

            await summary_repo.save(summary)

            child_type = _CHILD_SUMMARY_TYPE[summary.summary_type]
            child_summaries = await summary_repo.find_completed_in_range(
                user_id, child_type, summary.period_start, summary.period_end
            )

        # ── AI call (outside DB transaction) ─────────────────────────────────
        gemini = GeminiSummaryClient(settings.ai)
        prompt = build_prompt_from_summaries(summary.summary_type, child_summaries)
        content = await gemini.generate(prompt)

        # ── Transaction 2: complete + notify ─────────────────────────────────
        async with factory.begin() as session:
            summary_repo = RetroSummaryRepository(session)
            summary = await summary_repo.find_by_id(summary_id, user_id)
            summary.complete(content)
            await summary_repo.save(summary)

            if send_notification:
                notif_repo = NotificationRepository(session)
                period_name = _TYPE_KO.get(summary.summary_type, "")
                notification = Notification.create(
                    user_id=user_id,
                    type=NotificationType.SUCCESS,
                    category=NotificationCategory.SUMMARY,
                    title=f"{period_name} 회고 요약 완료",
                    message=f"{period_name} 회고 요약이 완료됐습니다.",
                )
                saved_notif = await notif_repo.save(notification)

        await redis.publish(
            f"summary:{summary_id}",
            json.dumps({"status": "completed", "summary_id": summary_id}),
        )
        if send_notification:
            await redis.publish(
                f"notifications:{user_id}",
                json.dumps({
                    "id": saved_notif.id,
                    "type": saved_notif.type.value,
                    "category": saved_notif.category.value,
                    "title": saved_notif.title,
                    "message": saved_notif.message,
                    "is_read": saved_notif.is_read,
                    "created_at": saved_notif.created_at.isoformat(),
                }),
            )

    except Exception:
        async with factory.begin() as session:
            summary_repo = RetroSummaryRepository(session)
            summary = await summary_repo.find_by_id(summary_id, user_id)
            if summary:
                summary.fail()
                await summary_repo.save(summary)

            if send_notification:
                notif_repo = NotificationRepository(session)
                notification = Notification.create(
                    user_id=user_id,
                    type=NotificationType.ERROR,
                    category=NotificationCategory.SUMMARY,
                    title="회고 요약 실패",
                    message="회고 요약 생성에 실패했습니다.",
                )
                saved_notif = await notif_repo.save(notification)

        if send_notification:
            await redis.publish(
                f"notifications:{user_id}",
                json.dumps({
                    "id": saved_notif.id,
                    "type": saved_notif.type.value,
                    "category": saved_notif.category.value,
                    "title": saved_notif.title,
                    "message": saved_notif.message,
                    "is_read": saved_notif.is_read,
                    "created_at": saved_notif.created_at.isoformat(),
                }),
            )
        await redis.publish(
            f"summary:{summary_id}",
            json.dumps({"status": "failed", "summary_id": summary_id}),
        )
        raise

    finally:
        await redis.aclose()
