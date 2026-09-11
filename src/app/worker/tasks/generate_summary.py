"""통합 summary 생성 task.

summary_type 별 데이터 소스 선택은 `strategies.get_strategy` 에 위임한다.
공통 골격(T1 mark in_progress / AI 호출 / T2 complete + notify / 실패 시 fail + notify) 만 task 본체에 있다.
"""
import json

import httpx
from celery import Task
from celery.exceptions import Retry
from celery.utils.time import get_exponential_backoff_interval
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

# 커밋 전이라 이 트랜잭션에 아직 안 보이는 summary row 를 만났을 때, 재시도 전 대기
# 시간(초). 실제 커밋 지연은 보통 수 ms 이므로 2초면 사실상 항상 해소된다 — 정책
# 값이 아니라 순수 기술적 안전 마진이라 env 화하지 않는다.
_NOT_YET_VISIBLE_RETRY_COUNTDOWN_SECONDS = 2

# Gemini 일시 장애(5xx)/타임아웃 재시도 백오프 파라미터. 예전 데코레이터 옵션이던
# `retry_backoff=True, retry_backoff_max=600, retry_jitter=True` 와 동일한 지수
# 백오프(초기 1초, 최대 600초, full jitter)를 self.retry() 수동 호출에서 재현한다 —
# 이유는 SummaryRowNotYetVisibleError 의 docstring 참고 (celery_aio_pool.AsyncIOPool
# 에서 autoretry_for 가 async task body 에 대해 실제로 작동하지 않는다). 이 값들도
# 운영 정책이 아니라 재시도 알고리즘 파라미터라 env 화하지 않는다 — 기존에도
# 하드코딩 데코레이터 인자였다.
_GEMINI_RETRY_BACKOFF_FACTOR = 1
_GEMINI_RETRY_BACKOFF_MAX_SECONDS = 600


class SummaryRowNotYetVisibleError(Exception):
    """summary row 가 이 트랜잭션에 아직 안 보일 때 (커밋 전 read) — 잠시 후 재시도.

    라우터는 BackgroundTasks 로 커밋 이후 enqueue 되도록 시도하지만, 이 스택
    (dishka `ContainerMiddleware` + Starlette)에서 BackgroundTasks 는 응답 전송
    직후 실행되고 요청 스코프 세션 커밋(`factory.begin()` 종료)은 그보다도 나중이라
    "커밋 후 실행"을 프레임워크만으로 보장할 방법이 없다. 그래서 순서 보장 대신
    워커가 짧게 재시도해서 흡수한다.

    **`autoretry_for` 가 아니라 `self.retry()` 를 직접 호출하는 이유**: 이 프로젝트의
    실제 워커 풀 `celery_aio_pool.AsyncIOPool` 에서는 `async def` task 에 대해
    `autoretry_for` 데코레이터가 사실상 작동하지 않는다 — `add_autoretry_behaviour`
    가 감싸는 `try/except` 는 `task._orig_run(*args, **kwargs)` 를 "호출"하는
    스레드 안에서만 실행되는데, 코루틴 함수를 호출하는 것은 코루틴 객체만 만들 뿐
    본문을 실행하지 않는다. `AsyncIOPool.run()` 은 그 결과(아직 await 안 된 코루틴)
    를 받아 재귀 호출로 실제 실행하므로, 본문에서 던진 예외는 그 재귀 프레임에서
    발생해 원래의 `try/except` 를 완전히 비껴간다 — 즉 예외는 그냥 태스크 실패로
    끝나고 재시도는 걸리지 않는다. 그래서 이 예외는 `find_by_id is None` 인 지점에서
    `raise self.retry(exc=SummaryRowNotYetVisibleError(...), countdown=...)` 로 직접
    재시도를 트리거한다 — `Task.retry()` 는 `Retry` 를 던지기 전에 `S.apply_async()`
    로 재큐잉을 동기적으로 수행하므로, 이 우회 문제와 무관하게 항상 실제로 재시도된다.
    `max_retries` 소진 시엔 `exc` 인자(이 예외)가 그대로 재발생해 `except Exception:`
    (FAILED 마킹 + 알림)으로 떨어진다 — 예전처럼 0.003초 만에 "성공"하고 PENDING 에
    영구히 멈춘 채 조용히 사라지지 않는다.
    """

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


def _notification_payload(notif: Notification, extra: dict | None = None) -> dict:
    payload = {
        "id": notif.id,
        "type": notif.type.value,
        "category": notif.category.value,
        "title": notif.title,
        "message": notif.message,
        "is_read": notif.is_read,
        "created_at": notif.created_at.isoformat(),
    }
    if extra:
        # SUMMARY 알림에 한해 어떤 요약이 갱신됐는지 식별 정보를 덧붙인다.
        # FE 가 /notifications/stream 구독만으로 해당 회고를 타깃 refetch 가능.
        payload.update(extra)
    return payload


@celery_app.task(
    name="worker.generate_summary",
    bind=True,
    rate_limit="60/m",
    # Gemini 5xx (특히 503 high-demand), 클라이언트 타임아웃(응답 stall), 커밋 전
    # row 조회(SummaryRowNotYetVisibleError) 모두 본문 안에서 직접 self.retry() 를
    # 호출해 재시도한다 — `autoretry_for` 는 여기 등록하지 않는다. 이 프로젝트의
    # 실제 워커 풀 celery_aio_pool.AsyncIOPool 에서는 async task body 에 대해
    # `autoretry_for` 데코레이터가 실제로 작동하지 않기 때문이다 (자세한 이유는
    # SummaryRowNotYetVisibleError 클래스 docstring 참고). 4xx 는 코드/요청 문제일
    # 가능성이 크므로 재시도 안 함.
    max_retries=5,
)
async def generate_summary_task(
    self: Task, summary_id: str, user_id: str, send_notification: bool = True
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
                raise self.retry(
                    exc=SummaryRowNotYetVisibleError(summary_id),
                    countdown=_NOT_YET_VISIBLE_RETRY_COUNTDOWN_SECONDS,
                )

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
                    # 활성 ID 가 살아있지 않으면 (예: 동시 삭제 race) 시스템 기본 fallback.
                    # 공백-only content 는 스타일 가이드로 의미가 없으므로 무시 (빈 템플릿 취급).
                    if (
                        template is not None
                        and template.summary_type == summary.summary_type
                        and template.content.strip()
                    ):
                        user_template = template.content

            strategy = get_strategy(summary.summary_type)
            prompt = await strategy.build_prompt(
                session, summary, user_template, locale
            )

        # AI 호출 — DB transaction 밖
        try:
            gemini = GeminiSummaryClient(settings.ai)
            content = await gemini.generate(prompt)
        except (genai_errors.ServerError, httpx.TimeoutException) as exc:
            # Gemini 일시 장애 / 응답 타임아웃 — 지수 백오프로 직접 재시도한다.
            # `autoretry_for` 로 위임하지 않는 이유는 아래 데코레이터 주석 참고.
            # 이 except 는 바깥 try 의 "body" 안에 중첩돼 있어야 한다 — 바깥
            # try 의 형제 except 절 안에 두면, max_retries 소진 시 self.retry()
            # 가 재발생시키는 원본 exc 가 이미 어느 except 블록 "안"이라 그 형제
            # 절들(`except Retry:`/`except Exception:`)로 다시 매칭되지 않고
            # 그냥 빠져나가 FAILED 마킹을 건너뛴 채 IN_PROGRESS 에 영구히
            # 멈춘다 — 실제로 재현해 확인한 회귀.
            countdown = get_exponential_backoff_interval(
                factor=_GEMINI_RETRY_BACKOFF_FACTOR,
                retries=self.request.retries,
                maximum=_GEMINI_RETRY_BACKOFF_MAX_SECONDS,
                full_jitter=True,
            )
            raise self.retry(exc=exc, countdown=countdown) from exc

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
            summary_meta = {
                "resource": "summary",
                "summaryId": summary_id,
                "summaryType": summary.summary_type.value,
                "summaryStatus": "completed",
                "periodStart": summary.period_start.isoformat(),
                "periodEnd": summary.period_end.isoformat(),
            }
            await redis.publish(
                f"notifications:{user_id}",
                json.dumps(_notification_payload(saved_notif, summary_meta)),
            )

    except Retry:
        # self.retry() 가 던진 것 (SummaryRowNotYetVisibleError 또는 Gemini
        # 재시도 중). FAILED 마킹·알림을 건너뛰어, 재시도 성공 시 사용자에게 실패
        # 알림이 가지 않게 한다. max_retries 소진 시엔 여기로 오지 않고 exc(원본
        # 예외)가 그대로 재발생해 아래 `except Exception:` 으로 떨어진다 — 의도된
        # 동작이다. (Gemini 예외는 위 중첩 try/except 에서 이미 self.retry() 로
        # 변환되므로, 여기서 별도로 다시 잡지 않는다 — 형제 except 안에서
        # self.retry() 를 부르면 소진 시 재발생하는 exc 가 이 형제 절들로 다시
        # 매칭되지 않고 그냥 빠져나가 FAILED 마킹을 건너뛰는 버그가 있었다.)
        raise
    except Exception:
        saved_notif = None
        failed_period_start = None
        failed_period_end = None
        async with factory.begin() as session:
            summary_repo = RetroSummaryRepository(session)
            summary = await summary_repo.find_by_id(summary_id, user_id)
            if summary is not None:
                summary.fail()
                await summary_repo.save(summary)
                failed_period_start = summary.period_start
                failed_period_end = summary.period_end

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
            summary_meta = {
                "resource": "summary",
                "summaryId": summary_id,
                "summaryStatus": "failed",
            }
            if summary_type_cached is not None:
                summary_meta["summaryType"] = summary_type_cached.value
            if failed_period_start is not None:
                summary_meta["periodStart"] = failed_period_start.isoformat()
            if failed_period_end is not None:
                summary_meta["periodEnd"] = failed_period_end.isoformat()
            await redis.publish(
                f"notifications:{user_id}",
                json.dumps(_notification_payload(saved_notif, summary_meta)),
            )
        await redis.publish(
            f"summary:{summary_id}",
            json.dumps({"status": "failed", "summary_id": summary_id}),
        )
        raise

    finally:
        await redis.aclose()
