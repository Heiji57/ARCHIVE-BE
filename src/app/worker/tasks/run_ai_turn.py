"""AI 대화 한 차례 — `POST /ai/conversations/{id}/messages` 가 enqueue 한다(ai_tasks 큐).

API 와 같은 Dishka 컨테이너로 유스케이스를 만든다(어댑터 배선을 한곳에서). 요청 스코프 하나가
트랜잭션 하나다 — 차례가 끝나 **커밋된 뒤** `done` 을 보내 FE 가 답을 다시 읽을 수 있게 한다.
제안(`proposal`) 이벤트는 커밋 전에 나가지만 제안 전체를 실어 보내므로 FE 가 다시 읽을 필요가 없다.
실패는 `error` 이벤트(code)로 알리고 끝낸다 — 사용자가 다시 보낼 수 있다(자동 재시도 없음).
"""

import json
from typing import Any

import structlog
from dishka import AsyncContainer, make_async_container
from redis.asyncio import Redis

from app.ai.application.use_cases.ai_settings import AiSettingsUseCase
from app.ai.application.use_cases.conversations import (
    ConversationsUseCase,
    MessageNotYetVisibleError,
    RunAiTurnUseCase,
)
from app.ai.domain.repositories.repository import IConversationRepository
from app.ai.infrastructure.container.providers import AiProvider
from app.ai.infrastructure.events import CommitAwareSink, RedisEventSink
from app.calendars.infrastructure.container.providers import CalendarsProvider
from app.data.infrastructure.container.providers import DataProvider
from app.notification.application.services.notifier import (
    STREAM_CHANNEL,
    Notifier,
    should_push_now,
    stream_payload,
)
from app.notification.domain.models.value_objects import NotificationCategory, NotificationType
from app.settings.domain.repositories.repository import IUserSettingsRepository
from app.shared.domain.exceptions.base import BaseAppException
from app.shared.domain.exceptions.external import AIServiceException
from app.shared.infrastructure.config.settings import get_settings
from app.shared.infrastructure.container.providers import AppProvider, RequestProvider
from app.worker.celery_app import celery_app

_log = structlog.get_logger(__name__)
_container: AsyncContainer | None = None


def _get_container() -> AsyncContainer:
    global _container
    if _container is None:
        _container = make_async_container(
            AppProvider(), RequestProvider(), CalendarsProvider(), AiProvider(), DataProvider()
        )
    return _container


_DONE_TEXT = {"ko": "예약한 일을 끝냈어요", "en": "Your scheduled task is done"}


async def _notify_schedule_result(conversation_id: str, user_id: str) -> None:
    """예약한 일의 결과 알림(category: schedule) — 제목은 예약 프롬프트, 누르면 그 대화로."""
    async with _get_container()() as request:
        conversation = await (await request.get(IConversationRepository)).find_by_id(
            conversation_id, user_id
        )
        settings = await (await request.get(IUserSettingsRepository)).find_by_user_id(user_id)
        lang = "ko" if (settings.locale if settings else "ko").startswith("ko") else "en"
        notification = await (await request.get(Notifier)).notify(
            user_id,
            type=NotificationType.INFO,
            category=NotificationCategory.SCHEDULE,
            title=(conversation.title if conversation else "AI")[:100],
            message=_DONE_TEXT[lang],
            link={"kind": "ai_conversation", "id": conversation_id},
        )
    if notification is not None and should_push_now(notification):
        redis = Redis.from_url(get_settings().redis.cache_url, decode_responses=True)
        try:
            await redis.publish(
                STREAM_CHANNEL.format(user_id=user_id), json.dumps(stream_payload(notification))
            )
        finally:
            await redis.aclose()


_VISIBILITY_RETRIES = 5


@celery_app.task(name="worker.run_ai_turn", bind=True, max_retries=_VISIBILITY_RETRIES)
async def run_ai_turn_task(
    self: Any,
    conversation_id: str,
    user_id: str,
    message_id: str | None = None,
    notify: bool = False,
) -> None:
    structlog.contextvars.bind_contextvars(user_id=user_id)
    redis = Redis.from_url(get_settings().redis.cache_url, decode_responses=True)
    sink = CommitAwareSink(RedisEventSink(redis, conversation_id))
    try:
        async with _get_container()() as request:
            options = await (await request.get(AiSettingsUseCase)).turn_options(user_id)
            use_case = await request.get(RunAiTurnUseCase)
            outcome, answer_id = await use_case.execute(
                user_id, conversation_id, sink, expect_message_id=message_id, **options
            )
        await sink.flush()  # 커밋 뒤 — 제안 행이 보이는 상태에서 카드를 띄운다
        await sink.emit(
            {"type": "done", "messageId": answer_id, "proposalIds": outcome.proposal_ids}
        )
    except MessageNotYetVisibleError as exc:
        # 요청 트랜잭션이 아직 커밋 전 — 요약 워커와 같은 방식으로 잠시 뒤 다시(AsyncContextTask).
        if self.request.retries < _VISIBILITY_RETRIES:
            raise self.retry(exc=exc, countdown=1) from exc
        await _fail(sink, conversation_id, user_id, "AI_CONVERSATION_NOT_FOUND")
        return
    except AIServiceException:
        _log.warning("run_ai_turn.llm_failed", conversation_id=conversation_id, exc_info=True)
        await _fail(sink, conversation_id, user_id, "AI_LLM_UNAVAILABLE")
        return
    except BaseAppException as e:
        await _fail(sink, conversation_id, user_id, e.code)
        return
    except Exception:
        # 태스크 최상위 경계 — 무엇이 깨져도 FE 가 '진행 중'에 매달리지 않게 error 를 보낸다.
        _log.exception("run_ai_turn.failed", conversation_id=conversation_id)
        await _fail(sink, conversation_id, user_id, "INTERNAL_ERROR")
        return
    finally:
        await redis.aclose()

    if notify:
        try:
            await _notify_schedule_result(conversation_id, user_id)
        except Exception:
            # 알림 실패가 이미 끝난 차례를 실패로 보이게 하지 않는다 — 기록만.
            _log.exception("run_ai_turn.notify_failed", conversation_id=conversation_id)


async def _fail(sink: CommitAwareSink, conversation_id: str, user_id: str, code: str) -> None:
    """롤백된 차례의 제안은 버리고, 실패를 기록한 뒤 error 를 보낸다."""
    sink.discard()
    try:
        async with _get_container()() as request:
            await (await request.get(ConversationsUseCase)).record_failure(
                user_id, conversation_id, code
            )
    except Exception:
        # 실패 기록마저 실패해도 error 이벤트는 보낸다.
        _log.exception("run_ai_turn.record_failure_failed", conversation_id=conversation_id)
    await sink.emit({"type": "error", "code": code})
