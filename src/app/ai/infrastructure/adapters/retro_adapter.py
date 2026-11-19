"""AI 포트 → 회고 모듈. 회고 초안 적용은 POST /entries 와 같은 규칙·후속 작업(임베딩)을 탄다."""

from typing import Any

from app.retrospective.application.dtos.commands import CreateEntryCommand
from app.retrospective.application.use_cases.create_entry import CreateEntryUseCase
from app.retrospective.application.use_cases.delete_entry import DeleteEntryUseCase
from app.retrospective.domain.repositories.repository import IJournalEntryRepository
from app.topic.domain.repositories.repository import IEmbeddingQueueRepository

_EXCERPT = 300


class RetroAdapter:
    def __init__(
        self,
        entry_repo: IJournalEntryRepository,
        create_uc: CreateEntryUseCase,
        delete_uc: DeleteEntryUseCase,
        queue_repo: IEmbeddingQueueRepository,
    ) -> None:
        self._entries = entry_repo
        self._create = create_uc
        self._delete = delete_uc
        self._queue = queue_repo

    async def search(self, user_id: str, query: str, limit: int) -> list[dict[str, Any]]:
        entries, _ = await self._entries.find_by_full_text(user_id, query, page=1, size=limit)
        return [
            {
                "id": e.id,
                "date": e.date_key,
                "type": e.retro_type.value,
                "title": e.title,
                "excerpt": e.content[:_EXCERPT],
            }
            for e in entries
        ]

    async def create_draft(self, user_id: str, date_key: str, content: str) -> str:
        entry = await self._create.execute(
            CreateEntryCommand(
                user_id=user_id, date_key=date_key, title=None, content=content, retro_type="daily"
            )
        )
        await self._queue.enqueue("entry", entry.id, user_id)
        return entry.id

    async def get(self, user_id: str, entry_id: str) -> dict[str, Any] | None:
        entry = await self._entries.find_by_id(entry_id, user_id)
        return {"id": entry.id, "content": entry.content} if entry else None

    async def delete(self, user_id: str, entry_id: str) -> None:
        # 일반 삭제와 같이 휴지통으로 — 청크는 남긴다(매칭에서만 빠지고, 되살리면 그대로 쓰인다).
        await self._delete.execute(entry_id=entry_id, user_id=user_id)
