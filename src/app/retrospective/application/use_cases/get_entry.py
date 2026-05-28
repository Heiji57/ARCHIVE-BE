from app.retrospective.domain.exceptions.exceptions import JournalEntryNotFoundException
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.repositories.repository import IJournalEntryRepository


class GetEntryUseCase:
    def __init__(self, entry_repo: IJournalEntryRepository) -> None:
        self._entry_repo = entry_repo

    async def execute(self, entry_id: str, user_id: str) -> JournalEntry:
        entry = await self._entry_repo.find_by_id(entry_id, user_id)
        if not entry:
            raise JournalEntryNotFoundException()
        return entry
