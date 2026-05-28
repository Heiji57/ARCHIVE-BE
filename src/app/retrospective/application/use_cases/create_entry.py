from datetime import datetime, timezone

from app.retrospective.application.dtos.commands import CreateEntryCommand
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.value_objects import RetroType
from app.retrospective.domain.repositories.repository import IJournalEntryRepository
from app.shared.domain.utils.id import generate_id


class CreateEntryUseCase:
    def __init__(self, entry_repo: IJournalEntryRepository) -> None:
        self._entry_repo = entry_repo

    async def execute(self, cmd: CreateEntryCommand) -> JournalEntry:
        now = datetime.now(timezone.utc)
        entry = JournalEntry(
            id=generate_id("entry"),
            user_id=cmd.user_id,
            date_key=cmd.date_key,
            title=cmd.title,
            content=cmd.content,
            retro_type=RetroType(cmd.retro_type),
            created_at=now,
        )
        return await self._entry_repo.save(entry)
