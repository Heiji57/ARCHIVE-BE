"""통합 summary 생성 task.

summary_type 별 데이터 소스 선택은 `strategies.get_strategy` 에 위임한다.
공통 골격(T1 mark in_progress / AI 호출 / T2 complete + notify / 실패 시 fail + notify) 만 task 본체에 있다.
"""
import json

from google.genai import errors as genai_errors
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
from app.retrospective.infrastructure.persistence.repositories.summary_template_repo import (
    UserSummaryTemplateRepository,
)
from app.settings.infrastructure.persistence.repositories.user_settings_repo import (
    UserSettingsRepository,
)
from app.shared.infrastructure.config.settings import get_settings
from app.worker.celery_app import celery_app
from app.worker.db import get_worker_session_factory

# 알림 텍스트는 사용자 locale 에 따라 분기 — 영어/한국어만 우선 지원, 그 외는 영어.
_NOTIFICATION_TEXT: dict[str, dict[SummaryType, dict[str, str]]] = {
    "ko": {
        SummaryType.WEEKLY: {"period": "주간", "success_title": "주간 회고 요약 완료",
                              "success_msg": "주간 회고 요약이 완료됐습니다.",
                              "fail_title": "주간 회고 요약 실패",
                              "fail_msg": "주간 회고 요약 생성에 실패했습니다."},
        SummaryType.MONTHLY: {"period": "월간", "success_title": "월간 회고 요약 완료",
                               "success_msg": "월간 회고 요약이 완료됐습니다.",
                               "fail_title": "월간 회고 요약 실패",
                               "fail_msg": "월간 회고 요약 생성에 실패했습니다."},
        SummaryType.ANNUAL: {"period": "연간", "success_title": "연간 회고 요약 완료",
                              "success_msg": "연간 회고 요약이 완료됐습니다.",
                              "fail_title": "연간 회고 요약 실패",
                              "fail_msg": "연간 회고 요약 생성에 실패했습니다."},
    },
    "en": {
        SummaryType.WEEKLY: {"period": "weekly", "success_title": "Weekly summary ready",
                              "success_msg": "Your weekly retrospective summary is ready.",
                              "fail_title": "Weekly summary failed",
                              "fail_msg": "Failed to generate weekly retrospective summary."},
        SummaryType.MONTHLY: {"period": "monthly", "success_title": "Monthly summary ready",
                               "success_msg": "Your monthly retrospective summary is ready.",
                               "fail_title": "Monthly summary failed",
                               "fail_msg": "Failed to generate monthly retrospective summary."},
        SummaryType.ANNUAL: {"period": "annual", "success_title": "Annual summary ready",
                              "success_msg": "Your annual retrospective summary is ready.",
                              "fail_title": "Annual summary failed",
                              "fail_msg": "Failed to generate annual retrospective summary."},
    },
}


def _notification_text(locale: str, summary_type: SummaryType) -> dict[str, str]:
    base = locale.split("-")[0].split("_")[0].strip().lower() if locale else "ko"
    return _NOTIFICATION_TEXT.get(base, _NOTIFICATION_TEXT["en"])[summary_type]


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


@celery_app.task(
    name="worker.generate_summary",
    rate_limit="60/m",
    # Gemini 5xx (특히 503 high-demand) 만 transient 로 보고 자동 재시도.
    # 4xx 는 코드/요청 문제일 가능성이 크므로 재시도하지 않음.
    autoretry_for=(genai_errors.ServerError,),
    retry_backoff=True,          # 지수 백오프
    retry_backoff_max=600,       # 최대 10분
    retry_jitter=True,           # 동시 재시도 분산
    max_retries=5,
)
async def generate_summary_task(
    summary_id: str, user_id: str, send_notification: bool = True
) -> None:
    settings = get_settings()
    factory = get_worker_session_factory()
    redis = Redis.from_url(settings.redis.cache_url, decode_responses=True)
    saved_notif: Notification | None = None

    locale = "ko"
    summary_type_cached: SummaryType | None = None

    try:
        # T1: mark in_progress + strategy 로 prompt 빌드 (사용자 settings 조회 포함)
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
            summary_type_cached = summary.summary_type

            user_settings_repo = UserSettingsRepository(session)
            user_settings = await user_settings_repo.find_by_user_id(user_id)
            user_template = ""
            if user_settings is not None:
                locale = user_settings.locale or "ko"
                active_template_id = user_settings.active_template_id_for(
                    summary.summary_type.value
                )
                if active_template_id:
                    template_repo = UserSummaryTemplateRepository(session)
                    template = await template_repo.find_by_id(active_template_id, user_id)
                    # 활성 ID 가 살아있지 않으면 (예: 동시 삭제 race) 시스템 기본 fallback
                    if template is not None and template.summary_type == summary.summary_type:
                        user_template = template.content

            strategy = get_strategy(summary.summary_type)
            prompt = await strategy.build_prompt(session, summary, user_template)

        # AI 호출 — DB transaction 밖
        gemini = GeminiSummaryClient(settings.ai)
        content = await gemini.generate(prompt, use_template_schema=bool(user_template))

        # T2: complete + notify
        async with factory.begin() as session:
            summary_repo = RetroSummaryRepository(session)
            summary = await summary_repo.find_by_id(summary_id, user_id)
            summary.complete(content)
            await summary_repo.save(summary)

            if send_notification:
                text = _notification_text(locale, summary.summary_type)
                notification = Notification.create(
                    user_id=user_id,
                    type=NotificationType.SUCCESS,
                    category=NotificationCategory.SUMMARY,
                    title=text["success_title"],
                    message=text["success_msg"],
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

    except genai_errors.ServerError:
        # Gemini 일시 장애 — Celery autoretry 로 위임. FAILED 마킹/알림 skip.
        raise
    except Exception:
        saved_notif = None
        async with factory.begin() as session:
            summary_repo = RetroSummaryRepository(session)
            summary = await summary_repo.find_by_id(summary_id, user_id)
            if summary is not None:
                summary.fail()
                await summary_repo.save(summary)

            if send_notification and summary_type_cached is not None:
                text = _notification_text(locale, summary_type_cached)
                notification = Notification.create(
                    user_id=user_id,
                    type=NotificationType.ERROR,
                    category=NotificationCategory.SUMMARY,
                    title=text["fail_title"],
                    message=text["fail_msg"],
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
