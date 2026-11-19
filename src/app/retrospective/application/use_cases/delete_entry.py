from app.retrospective.domain.exceptions.exceptions import JournalEntryNotFoundException
from app.retrospective.domain.repositories.repository import IJournalEntryRepository


class DeleteEntryUseCase:
    def __init__(self, entry_repo: IJournalEntryRepository) -> None:
        self._entry_repo = entry_repo

    async def execute(self, entry_id: str, user_id: str) -> None:
        entry = await self._entry_repo.find_by_id(entry_id, user_id)
        if not entry:
            raise JournalEntryNotFoundException()
        # 휴지통으로 — 청크는 남긴다(매칭에서는 빠지고, 되살리면 다시 임베딩하지 않는다).
        await self._entry_repo.soft_delete(entry_id, user_id)
