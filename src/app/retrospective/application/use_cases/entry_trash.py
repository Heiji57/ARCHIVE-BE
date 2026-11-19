"""회고 휴지통 — 목록·되살리기·영구 삭제. 휴지통 API(`data` 모듈)가 부른다.

- 휴지통의 회고 청크는 지우지 않고 매칭에서만 뺀다 — 되살릴 때 다시 임베딩하지 않게.
- 폴더가 없어졌으면 미분류로 돌아온다(folder_id 는 FK SET NULL 로 이미 비어 있음).
- 같은 날·종류의 새 회고가 있으면 되살릴 수 없다(409 JOURNAL_ENTRY_ALREADY_EXISTS).
- 영구 삭제는 `entry_chunks` 도 지운다(FK 가 없다).
"""

from datetime import datetime

from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.repositories.repository import IJournalEntryRepository
from app.topic.domain.repositories.repository import IEntryChunkRepository


class EntryTrashUseCase:
    def __init__(
        self, entry_repo: IJournalEntryRepository, chunk_repo: IEntryChunkRepository
    ) -> None:
        self._repo = entry_repo
        self._chunk_repo = chunk_repo

    async def list(self, user_id: str) -> list[JournalEntry]:
        return await self._repo.list_trashed(user_id)

    async def restore(self, user_id: str, entry_id: str) -> JournalEntry | None:
        trashed = await self._repo.find_trashed(entry_id, user_id)
        if trashed is None:
            return None
        await self._repo.restore(entry_id, user_id)
        return trashed

    async def purge(self, user_id: str, entry_id: str) -> bool:
        ids = await self._repo.purge(entry_id, user_id)
        await self._chunk_repo.delete_by_entries(ids)
        return bool(ids)

    async def purge_all(self, user_id: str | None, before: datetime | None = None) -> int:
        ids = await self._repo.purge_trashed(user_id, before)
        await self._chunk_repo.delete_by_entries(ids)
        return len(ids)
