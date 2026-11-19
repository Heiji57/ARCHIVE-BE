"""행동 학습 — 기록 남기기, 통계(모델) 꺼내기, 지우기.

- 학습을 끄면(`ai_settings.learning_enabled = false`) 기록을 남기지 않고 모델도 쓰지 않는다.
- 통계는 `ai_user_models` 에 캐시한다. 새 기록이 들어오면 stale 이 되고, 다음에 꺼낼 때
  최근 `EVENT_RETENTION_DAYS` 기록으로 다시 계산한다. 감쇠·'무시' 판정이 날짜에 따라 바뀌므로
  `_MAX_AGE` 가 지나도 다시 계산한다.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.ai.domain.models.learning import (
    EVENT_RETENTION_DAYS,
    BehaviorEvent,
    BehaviorEventType,
    BehaviorModel,
    LearningMetrics,
)
from app.ai.domain.models.snapshots import TodoSnapshot
from app.ai.domain.repositories.repository import IAiSettingsRepository, IBehaviorRepository
from app.ai.domain.services.behavior_model import build_model, learning_metrics
from app.ai.domain.services.suggestion_ranker import context_of

_MAX_AGE = timedelta(hours=6)
_METRICS_DAYS = 30


@dataclass(frozen=True)
class EventContext:
    """기록 한 건을 남길 때의 사용자 시각."""

    now: datetime  # UTC
    tz: ZoneInfo

    @property
    def local(self) -> datetime:
        return self.now.astimezone(self.tz)

    @property
    def day(self) -> str:
        return self.local.date().isoformat()

    @property
    def ctx(self) -> dict[str, str]:
        return context_of(self.local)


class LearningService:
    def __init__(self, repo: IBehaviorRepository, settings_repo: IAiSettingsRepository) -> None:
        self._repo = repo
        self._settings_repo = settings_repo
        self._enabled: dict[str, bool] = {}

    async def enabled(self, user_id: str) -> bool:
        if user_id not in self._enabled:
            settings = await self._settings_repo.find(user_id)
            self._enabled[user_id] = settings.learning_enabled if settings else True
        return self._enabled[user_id]

    async def record(
        self,
        user_id: str,
        type_: BehaviorEventType,
        at: EventContext,
        data: dict[str, Any],
        todo_id: str | None = None,
    ) -> None:
        if not await self.enabled(user_id):
            return
        # '보임' 은 그날이 지나야 '무시' 로 셈에 들어가 바로 다시 계산할 필요가 없다
        # (_MAX_AGE 가 맡음) — 추천을 부를 때마다 통계를 다시 계산하지 않게.
        await self._repo.add_event(
            user_id,
            BehaviorEvent(type=type_, created_at=at.now, todo_id=todo_id, data=data),
            mark_stale=type_ != "sugg_shown",
        )

    async def model(self, user_id: str, today: date, now: datetime) -> BehaviorModel | None:
        """학습을 껐으면 None. 캐시가 stale·오래됐으면 다시 계산해 저장한다."""
        if not await self.enabled(user_id):
            return None
        cached = await self._repo.find_model(user_id)
        if cached is not None:
            model, computed_at, stale = cached
            if not stale and now - computed_at < _MAX_AGE:
                return model
        events = await self._repo.list_events_since(
            user_id, now - timedelta(days=EVENT_RETENTION_DAYS)
        )
        model = build_model(events, now, today)
        await self._repo.save_model(user_id, model, now)
        return model

    async def metrics(self, user_id: str, today: date, now: datetime) -> LearningMetrics:
        enabled = await self.enabled(user_id)
        model = await self.model(user_id, today, now) if enabled else None
        events = await self._repo.list_events_since(user_id, now - timedelta(days=_METRICS_DAYS))
        return learning_metrics(events, enabled, ready=bool(model and model.can_rank))

    async def reset(self, user_id: str) -> None:
        await self._repo.reset(user_id)

    async def todo_changed(
        self, user_id: str, before: TodoSnapshot, after: TodoSnapshot, at: EventContext
    ) -> None:
        """할 일 하나를 고친 뒤 — 끝냄, 날짜 옮김, 시간 정함·옮김을 기록한다."""
        if not await self.enabled(user_id):
            return
        tag = after.tag
        minutes = (
            int((after.end_time - after.start_time).total_seconds() // 60)  # type: ignore[operator]
            if after.is_timed
            else None
        )
        if after.status == "done" and before.status != "done":
            started = after.start_time.astimezone(at.tz).hour if after.start_time else None
            await self.record(
                user_id,
                "todo_done",
                at,
                {
                    "hour": started if started is not None else at.local.hour,
                    "minutes": minutes,
                    "tag": tag,
                    "day": at.day,
                },
                todo_id=after.id,
            )
            return  # 끝내면서 바꾼 날짜·시간은 "옮김" 이 아니다
        if not after.is_open:
            return
        if after.date_key != before.date_key:
            await self.record(
                user_id,
                "todo_moved",
                at,
                {"from": before.date_key, "to": after.date_key, "tag": tag},
                todo_id=after.id,
            )
        if after.is_timed and after.start_time != before.start_time:
            await self.record(
                user_id,
                "todo_retimed",
                at,
                {
                    "hour": after.start_time.astimezone(at.tz).hour,  # type: ignore[union-attr]
                    "minutes": minutes,
                    "tag": tag,
                },
                todo_id=after.id,
            )


def event_context(tz: ZoneInfo, now: datetime | None = None) -> EventContext:
    return EventContext(now=(now or datetime.now(UTC)).astimezone(UTC), tz=tz)
