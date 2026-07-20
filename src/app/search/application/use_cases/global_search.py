import asyncio
from dataclasses import dataclass

from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.repositories.repository import IJournalEntryRepository
from app.todo.domain.models.todo import Todo
from app.todo.domain.repositories.repository import ITodoRepository


@dataclass(frozen=True)
class GlobalSearchResult:
    todos: list[Todo]
    entries: list[JournalEntry]


class GlobalSearchUseCase:
    """nav 통합검색 — Todo 와 회고 entry(daily) 를 동시에 검색한다.

    두 리소스의 tsvector 관련도 점수는 서로 비교 불가능하므로 하나로 억지로 합치지
    않고, 타입별로 상위 N개씩 나눠서 반환한다(FE 가 섹션별로 렌더).
    """

    def __init__(self, todo_repo: ITodoRepository, entry_repo: IJournalEntryRepository) -> None:
        self._todo_repo = todo_repo
        self._entry_repo = entry_repo

    async def execute(self, user_id: str, q: str, limit: int) -> GlobalSearchResult:
        (todos, _), (entries, _) = await asyncio.gather(
            self._todo_repo.find_by_full_text(user_id, q, page=1, size=limit),
            self._entry_repo.find_by_full_text(user_id, q, page=1, size=limit),
        )
        return GlobalSearchResult(todos=todos, entries=entries)
