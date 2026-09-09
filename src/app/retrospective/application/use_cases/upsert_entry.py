from datetime import datetime, timezone

from app.retrospective.application.dtos.commands import UpsertEntryCommand
from app.retrospective.domain.constants.entry_title_defaults import resolve_entry_title
from app.retrospective.domain.exceptions.exceptions import (
    JournalEntryAlreadyExistsException,
    JournalEntryNotFoundException,
)
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.value_objects import RetroType
from app.retrospective.domain.repositories.repository import IJournalEntryRepository
from app.settings.domain.repositories.repository import IUserSettingsRepository


class UpsertEntryUseCase:
    """PUT /entries/:id — id로 조회 후 없으면 생성, 있으면 수정."""

    def __init__(
        self,
        entry_repo: IJournalEntryRepository,
        settings_repo: IUserSettingsRepository,
    ) -> None:
        self._entry_repo = entry_repo
        self._settings_repo = settings_repo

    async def _resolve_title(self, cmd: UpsertEntryCommand) -> str:
        if cmd.title and cmd.title.strip():
            return cmd.title
        settings = await self._settings_repo.find_by_user_id(cmd.user_id)
        return resolve_entry_title(
            cmd.title,
            cmd.date_key,
            RetroType(cmd.retro_type),
            settings.locale if settings else None,
        )

    async def execute(self, cmd: UpsertEntryCommand) -> JournalEntry:
        existing = await self._entry_repo.find_by_id(cmd.entry_id, cmd.user_id)

        if existing:
            existing.title = await self._resolve_title(cmd)
            existing.content = cmd.content
            existing.retro_type = RetroType(cmd.retro_type)
            existing.date_key = cmd.date_key
            existing.updated_at = datetime.now(timezone.utc)
            return await self._entry_repo.save(existing)

        # 스코프 조회가 None 이어도 그 id 가 '남의 엔트리'면 생성 분기의 save(merge)가
        # PK 로 타 유저 행을 덮어써 탈취된다(BOLA). 전역 존재 확인으로 남의 것이면 404 로
        # 거절 — 진짜 빈 id 일 때만 생성한다. (본인 미존재 id 로의 신규 생성은 그대로 허용.)
        if await self._entry_repo.id_exists(cmd.entry_id):
            raise JournalEntryNotFoundException()

        # create_entry.py(POST)와 동일한 사전 체크 — 없으면 (user, date_key, retro_type)
        # DB 유니크 제약(uq_journal_entries_user_date_retro_type) 위반이 처리 안 된
        # IntegrityError 로 500 이 된다.
        if await self._entry_repo.find_by_date_key(
            cmd.user_id, cmd.date_key, cmd.retro_type
        ):
            raise JournalEntryAlreadyExistsException()

        now = datetime.now(timezone.utc)
        new_entry = JournalEntry(
            id=cmd.entry_id,
            user_id=cmd.user_id,
            date_key=cmd.date_key,
            title=await self._resolve_title(cmd),
            content=cmd.content,
            retro_type=RetroType(cmd.retro_type),
            created_at=now,
        )
        return await self._entry_repo.save(new_entry)
