from dataclasses import dataclass, field
from typing import Literal

from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.repositories.repository import IJournalEntryRepository
from app.todo.domain.models.todo import Todo
from app.todo.domain.repositories.repository import ITodoRepository
from app.topic.domain.models.topic import Topic
from app.topic.domain.repositories.repository import ITopicRepository

SearchScope = Literal["all", "todo", "retro", "topic"]


@dataclass(frozen=True)
class GlobalSearchResult:
    todos: list[Todo] = field(default_factory=list)
    entries: list[JournalEntry] = field(default_factory=list)
    topics: list[Topic] = field(default_factory=list)


class GlobalSearchUseCase:
    """통합검색 — Todo, 회고(모든 종류), 주제를 범위(scope)별로 검색한다.

    리소스마다 관련도 점수를 비교할 수 없으므로 하나로 합치지 않고, 종류별로 상위
    `limit`개씩 나눠 반환한다(FE 가 섹션별로 렌더). 범위 밖 종류는 빈 목록.

    세 리포지토리가 요청 스코프 세션 하나를 공유하므로 순서대로 조회한다 —
    AsyncSession 은 동시 실행(asyncio.gather)을 지원하지 않는다.
    """

    def __init__(
        self,
        todo_repo: ITodoRepository,
        entry_repo: IJournalEntryRepository,
        topic_repo: ITopicRepository,
    ) -> None:
        self._todo_repo = todo_repo
        self._entry_repo = entry_repo
        self._topic_repo = topic_repo

    async def execute(
        self, user_id: str, q: str, limit: int, scope: SearchScope = "all"
    ) -> GlobalSearchResult:
        todos: list[Todo] = []
        entries: list[JournalEntry] = []
        topics: list[Topic] = []
        if scope in ("all", "todo"):
            todos = await self._todos(user_id, q, limit)
        if scope in ("all", "retro"):
            entries = await self._entries(user_id, q, limit)
        if scope in ("all", "topic"):
            topics = await self._topic_repo.search(user_id, q, limit)
        return GlobalSearchResult(todos=todos, entries=entries, topics=topics)

    async def _todos(self, user_id: str, q: str, limit: int) -> list[Todo]:
        todos, _ = await self._todo_repo.find_by_full_text(user_id, q, page=1, size=limit)
        return todos

    async def _entries(self, user_id: str, q: str, limit: int) -> list[JournalEntry]:
        entries, _ = await self._entry_repo.find_by_full_text(user_id, q, page=1, size=limit)
        return entries
