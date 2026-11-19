"""AI 설정(5c) — 시트 값, 알려 둔 것(기억), 예약한 일."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from app.ai.domain.exceptions.exceptions import (
    AiMemoryLimitExceededException,
    AiMemoryNotFoundException,
    AiScheduleLimitExceededException,
    AiScheduleNotFoundException,
)
from app.ai.domain.models.ai_settings import (
    MAX_MEMORIES,
    MAX_SCHEDULES,
    SOURCES,
    AiMemory,
    AiSchedule,
    AiSettings,
)
from app.ai.domain.repositories.repository import IAiSettingsRepository
from app.shared.domain.utils.id import generate_id


class AiSettingsUseCase:
    def __init__(self, repo: IAiSettingsRepository) -> None:
        self._repo = repo

    # ── 시트 ──────────────────────────────────────────────────────────────
    async def get(self, user_id: str) -> AiSettings:
        return await self._repo.find(user_id) or AiSettings.default(user_id)

    async def patch(self, user_id: str, changes: dict[str, Any]) -> AiSettings:
        """보낸 필드만. tools 는 보낸 출처만 병합한다."""
        current = await self.get(user_id)
        if "tools" in changes:
            changes = {**changes, "tools": {**current.tools, **changes["tools"]}}
            changes["tools"] = {s: bool(changes["tools"].get(s, True)) for s in SOURCES}
        changes.pop("confirm_mode", None)  # 1차는 항상 확인 — 자동 적용은 2차
        return await self._repo.save(replace(current, **changes))

    async def turn_options(self, user_id: str) -> dict[str, Any]:
        """대화 한 차례에 넘길 값 — 켠 출처, 기억(켰을 때만), 답하는 방식."""
        settings = await self.get(user_id)
        memories = (
            [m.text for m in await self._repo.list_memories(user_id)]
            if settings.memory_enabled
            else []
        )
        return {
            "enabled_sources": settings.enabled_sources(),
            "memories": memories,
            "answer_length": settings.answer_length,
        }

    # ── 알려 둔 것 ────────────────────────────────────────────────────────
    async def memories(self, user_id: str) -> list[AiMemory]:
        return await self._repo.list_memories(user_id)

    async def add_memory(self, user_id: str, text: str) -> AiMemory:
        if len(await self._repo.list_memories(user_id)) >= MAX_MEMORIES:
            raise AiMemoryLimitExceededException(f"At most {MAX_MEMORIES} memories.")
        return await self._repo.add_memory(
            AiMemory(
                id=generate_id("mem"), user_id=user_id, text=text, created_at=datetime.now(UTC)
            )
        )

    async def delete_memory(self, user_id: str, memory_id: str) -> None:
        if not await self._repo.delete_memory(memory_id, user_id):
            raise AiMemoryNotFoundException()

    # ── 예약한 일 ─────────────────────────────────────────────────────────
    async def schedules(self, user_id: str) -> list[AiSchedule]:
        return await self._repo.list_schedules(user_id)

    async def create_schedule(
        self, user_id: str, prompt: str, repeat: dict[str, Any], enabled: bool
    ) -> AiSchedule:
        if len(await self._repo.list_schedules(user_id)) >= MAX_SCHEDULES:
            raise AiScheduleLimitExceededException(f"At most {MAX_SCHEDULES} schedules.")
        now = datetime.now(UTC)
        return await self._repo.save_schedule(
            AiSchedule(
                id=generate_id("sched"),
                user_id=user_id,
                prompt=prompt,
                repeat=repeat,
                enabled=enabled,
                created_at=now,
                updated_at=now,
            )
        )

    async def update_schedule(
        self, user_id: str, schedule_id: str, changes: dict[str, Any]
    ) -> AiSchedule:
        schedule = await self._repo.find_schedule(schedule_id, user_id)
        if schedule is None:
            raise AiScheduleNotFoundException()
        return await self._repo.save_schedule(
            replace(schedule, **changes, updated_at=datetime.now(UTC))
        )

    async def delete_schedule(self, user_id: str, schedule_id: str) -> None:
        if not await self._repo.delete_schedule(schedule_id, user_id):
            raise AiScheduleNotFoundException()
