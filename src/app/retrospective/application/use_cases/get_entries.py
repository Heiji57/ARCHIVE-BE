from datetime import date

from app.retrospective.application.dtos.queries import GetEntriesQuery
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.repositories.repository import IJournalEntryRepository


class GetEntriesUseCase:
    def __init__(self, entry_repo: IJournalEntryRepository) -> None:
        self._entry_repo = entry_repo

    async def execute(self, query: GetEntriesQuery) -> list[JournalEntry]:
        if query.retro_type:
            return await self._entry_repo.find_by_retro_type(query.user_id, query.retro_type)

        if query.from_date and query.to_date:
            return await self._entry_repo.find_by_period(
                query.user_id,
                date.fromisoformat(query.from_date),
                date.fromisoformat(query.to_date),
            )

        return []
