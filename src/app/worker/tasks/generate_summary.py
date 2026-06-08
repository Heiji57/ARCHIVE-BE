"""통합 summary 생성 task.

summary_type 별 데이터 소스 선택은 `strategies.get_strategy` 에 위임한다.
공통 골격(T1 mark in_progress / AI 호출 / T2 complete + notify / 실패 시 fail + notify) 만 task 본체에 있다.
"""
import json

from redis.asyncio import Redis

from app.notification.domain.models.notification import Notification
from app.notification.domain.models.value_objects import NotificationCategory, NotificationType
from app.notification.infrastructure.persistence.repositories.notification_repo import (
    NotificationRepository,
)
from app.retrospective.domain.exceptions.exceptions import (
    SummaryAlreadyInProgressException,
    SummaryInvalidStateException,
)
from app.retrospective.domain.models.value_objects import SummaryType
from app.retrospective.infrastructure.ai.gemini_client import GeminiSummaryClient
from app.retrospective.infrastructure.ai.strategies import get_strategy
from app.retrospective.infrastructure.persistence.repositories.retro_summary_repo import (
    RetroSummaryRepository,
)
from app.shared.infrastructure.config.settings import get_settings
from app.worker.celery_app import celery_app
from app.worker.db import get_worker_session_factory

_TYPE_KO = {
    SummaryType.WEEKLY: "주간",
    SummaryType.MONTHLY: "월간",
    SummaryType.ANNUAL: "연간",
}


def _notification_payload(notif: Notification) -> dict:
    return {
        "id": notif.id,
        "type": notif.type.value,
        "category": notif.category.value,
        "title": notif.title,
        "message": notif.message,
        "is_read": notif.is_read,
        "created_at": notif.created_at.isoformat(),
    }


@celery_app.task(name="worker.generate_summary", rate_limit="60/m")
async def generate_summary_task(
    summary_id: str, user_id: str, send_notification: bool = True
) -> None:
    settings = get_settings()
    factory = get_worker_session_factory()
    redis = Redis.from_url(settings.redis.cache_url, decode_responses=True)
    saved_notif: Notification | None = None

    try:
        # T1: mark in_progress + strategy 로 prompt 빌드
        async with factory.begin() as session:
            summary_repo = RetroSummaryRepository(session)
            summary = await summary_repo.find_by_id(summary_id, user_id)
            if summary is None:
                return

            try:
                summary.mark_in_progress()
            except (SummaryAlreadyInProgressException, SummaryInvalidStateException):
                return  # 중복 또는 이미 완료 — silent skip

            await summary_repo.save(summary)

            strategy = get_strategy(summary.summary_type)
            prompt = await strategy.build_prompt(session, summary)

        # AI 호출 — DB transaction 밖
        gemini = GeminiSummaryClient(settings.ai)
        content = await gemini.generate(prompt)

        # T2: complete + notify
        async with factory.begin() as session:
            summary_repo = RetroSummaryRepository(session)
            summary = await summary_repo.find_by_id(summary_id, user_id)
            summary.complete(content)
            await summary_repo.save(summary)

            if send_notification:
                period_name = _TYPE_KO.get(summary.summary_type, "")
                notification = Notification.create(
                    user_id=user_id,
                    type=NotificationType.SUCCESS,
                    category=NotificationCategory.SUMMARY,
                    title=f"{period_name} 회고 요약 완료",
                    message=f"{period_name} 회고 요약이 완료됐습니다.",
                )
                saved_notif = await NotificationRepository(session).save(notification)

        await redis.publish(
            f"summary:{summary_id}",
            json.dumps({"status": "completed", "summary_id": summary_id}),
        )
        if saved_notif is not None:
            await redis.publish(
                f"notifications:{user_id}",
                json.dumps(_notification_payload(saved_notif)),
            )

    except Exception:
        saved_notif = None
        async with factory.begin() as session:
            summary_repo = RetroSummaryRepository(session)
            summary = await summary_repo.find_by_id(summary_id, user_id)
            if summary is not None:
                summary.fail()
                await summary_repo.save(summary)

            if send_notification:
                notification = Notification.create(
                    user_id=user_id,
                    type=NotificationType.ERROR,
                    category=NotificationCategory.SUMMARY,
                    title="회고 요약 실패",
                    message="회고 요약 생성에 실패했습니다.",
                )
                saved_notif = await NotificationRepository(session).save(notification)

        if saved_notif is not None:
            await redis.publish(
                f"notifications:{user_id}",
                json.dumps(_notification_payload(saved_notif)),
            )
        await redis.publish(
            f"summary:{summary_id}",
            json.dumps({"status": "failed", "summary_id": summary_id}),
        )
        raise

    finally:
        await redis.aclose()
