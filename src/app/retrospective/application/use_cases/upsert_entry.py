from datetime import datetime, timezone

from app.retrospective.application.dtos.commands import UpsertEntryCommand
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.value_objects import RetroType
from app.retrospective.domain.repositories.repository import IJournalEntryRepository
from app.shared.domain.utils.id import generate_id


class UpsertEntryUseCase:
    """PUT /entries/:id — id로 조회 후 없으면 생성, 있으면 수정."""

    def __init__(self, entry_repo: IJournalEntryRepository) -> None:
        self._entry_repo = entry_repo

    async def execute(self, cmd: UpsertEntryCommand) -> JournalEntry:
        existing = await self._entry_repo.find_by_id(cmd.entry_id, cmd.user_id)

        if existing:
            existing.title = cmd.title
            existing.content = cmd.content
            existing.retro_type = RetroType(cmd.retro_type)
            existing.date_key = cmd.date_key
            existing.updated_at = datetime.now(timezone.utc)
            return await self._entry_repo.save(existing)

        now = datetime.now(timezone.utc)
        new_entry = JournalEntry(
            id=cmd.entry_id,
            user_id=cmd.user_id,
            date_key=cmd.date_key,
            title=cmd.title,
            content=cmd.content,
            retro_type=RetroType(cmd.retro_type),
            created_at=now,
        )
        return await self._entry_repo.save(new_entry)
