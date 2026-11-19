"""AI 예약한 일과 대화 기록 정리.

- `worker.dispatch_ai_schedules`(5분): 시각이 된 예약을 대화로 한 차례 돌린다.
  예약마다 새 대화를 만들고 프롬프트를 사용자 메시지로 넣은 뒤
  `worker.run_ai_turn`(notify=True)에 맡긴다. 결과는 `category: schedule` 알림
  (링크 = 그 대화)으로 간다. 만들어진 제안은 사용자가 알림에서 열어 적용한다.
- `worker.purge_ai_conversations`(하루): 사용자 `retention_days` 보다 오래된 대화와
  적용 안 한 제안을
  지운다. 0(보관 안 함)은 하루 지난 것을 지운다. 행동 학습 기록은 대화 보관 기간과 따로
  `EVENT_RETENTION_DAYS`(180일 — 반감기 30일이라 그보다 오래된 기록은 무게가 거의 없다)가
  지나면 지운다.

예약마다 요청 스코프(트랜잭션) 하나 — 한 예약의 실패가 다른 예약을 막지 않는다.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy import select

from app.ai.application.use_cases.conversations import ConversationsUseCase, PostMessageUseCase
from app.ai.application.use_cases.usage import AiUsageService
from app.ai.domain.exceptions.exceptions import AiUsageLimitExceededException
from app.ai.domain.models.ai_settings import AiSettings
from app.ai.domain.models.learning import EVENT_RETENTION_DAYS
from app.ai.domain.repositories.repository import (
    IAiRetentionRepository,
    IAiSettingsRepository,
    IBehaviorRepository,
)
from app.ai.domain.services.schedule_rules import schedule_due
from app.user.domain.repositories.repository import IUserRepository
from app.user.infrastructure.persistence.models.user_model import UserModel
from app.worker.celery_app import celery_app
from app.worker.tasks.run_ai_turn import _get_container

_log = structlog.get_logger(__name__)


@celery_app.task(name="worker.dispatch_ai_schedules")
async def dispatch_ai_schedules_task() -> None:
    from app.worker.tasks.run_ai_turn import run_ai_turn_task

    container = _get_container()
    async with container() as request:
        schedules = await (await request.get(IAiSettingsRepository)).list_enabled_schedules()

    now = datetime.now(UTC)
    for schedule in schedules:
        try:
            enqueue: tuple[str, str] | None = None
            async with container() as request:
                user = await (await request.get(IUserRepository)).find_by_id(schedule.user_id)
                if user is None:
                    continue
                try:
                    local_now = now.astimezone(ZoneInfo(user.timezone))
                except (ZoneInfoNotFoundError, ValueError):
                    continue
                if not schedule_due(schedule, local_now):
                    continue
                # 사용량을 먼저 본다 — 넘었으면 빈 대화를 만들지 않고 그날은 건너뛴다.
                usage = await request.get(AiUsageService)
                try:
                    await usage.check(schedule.user_id)
                except AiUsageLimitExceededException:
                    _log.info("ai_schedule.quota_exceeded", schedule_id=schedule.id)
                    await (await request.get(IAiSettingsRepository)).claim_run(
                        schedule.id, local_now.date()
                    )
                    continue
                # 조건부 UPDATE 로 오늘 차례를 가져간다 — 두 번 돌아도 한 번만, 그사이 사용자가
                # 바꾼 프롬프트·켜짐 같은 다른 필드는 덮지 않는다.
                if not await (await request.get(IAiSettingsRepository)).claim_run(
                    schedule.id, local_now.date()
                ):
                    continue
                conversation = await (await request.get(ConversationsUseCase)).create(
                    schedule.user_id, schedule.prompt
                )
                message = await (await request.get(PostMessageUseCase)).execute(
                    schedule.user_id,
                    conversation.id,
                    schedule.prompt,
                    {"scheduleId": schedule.id},
                )
                enqueue = (conversation.id, message.id)
            if enqueue is not None:
                run_ai_turn_task.apply_async(
                    args=[enqueue[0], schedule.user_id, enqueue[1]],
                    kwargs={"notify": True},
                    queue="ai_tasks",
                )
        except Exception:
            # 예약별 격리 경계 — 한 예약의 실패가 다른 사용자의 예약을 막지 않게.
            _log.exception("ai_schedule.failed", schedule_id=schedule.id)


@celery_app.task(name="worker.purge_ai_conversations")
async def purge_ai_conversations_task() -> None:
    container = _get_container()
    async with container() as request:
        session_users = await _user_ids(request)
    now = datetime.now(UTC)
    for user_id in session_users:
        try:
            async with container() as request:
                settings = await (await request.get(IAiSettingsRepository)).find(user_id)
                days = (settings or AiSettings.default(user_id)).retention_days or 1
                removed = await (await request.get(IAiRetentionRepository)).purge_older_than(
                    user_id, now - timedelta(days=days)
                )
                if removed:
                    _log.info("ai_retention.purged", user_id=user_id, conversations=removed)
        except Exception:
            # 사용자별 격리 경계
            _log.exception("ai_retention.failed", user_id=user_id)
    async with container() as request:
        events = await (await request.get(IBehaviorRepository)).purge_before(
            now - timedelta(days=EVENT_RETENTION_DAYS)
        )
    if events:
        _log.info("ai_learning.purged", events=events)


async def _user_ids(request) -> list[str]:  # type: ignore[no-untyped-def]
    from sqlalchemy.ext.asyncio import AsyncSession

    session = await request.get(AsyncSession)
    return list((await session.execute(select(UserModel.id))).scalars())
