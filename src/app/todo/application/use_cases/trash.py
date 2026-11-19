"""할 일 휴지통 — 목록·되살리기·영구 삭제. 휴지통 API(`data` 모듈)가 부른다.

- 시리즈는 base 한 건으로 보이고, base 와 예외 row 가 함께 들어가고 함께 나온다.
- 지울 때 Google 일정은 지웠으므로, 되살리면 연동 흔적(`google_event_id`)을 비우고
  자동 보내기 조건(`auto_push_enabled`)이면 새 일정으로 다시 보낸다.
- 영구 삭제는 `todo_embeddings` 도 지운다(FK 가 없다).
"""

from dataclasses import dataclass
from datetime import datetime

from app.calendars.domain.repositories.repository import ICalendarRepository
from app.settings.domain.repositories.repository import IUserSettingsRepository
from app.todo.application.services.auto_push import auto_push_enabled
from app.todo.domain.models.todo import Todo
from app.todo.domain.repositories.repository import ITodoRepository
from app.topic.domain.repositories.repository import ITodoEmbeddingRepository


@dataclass(frozen=True)
class RestoredTodo:
    todo: Todo
    push: bool  # 라우터가 push task 를 enqueue 해야 함


class TodoTrashUseCase:
    def __init__(
        self,
        todo_repo: ITodoRepository,
        settings_repo: IUserSettingsRepository,
        calendar_repo: ICalendarRepository,
        embedding_repo: ITodoEmbeddingRepository,
    ) -> None:
        self._repo = todo_repo
        self._settings_repo = settings_repo
        self._calendar_repo = calendar_repo
        self._embedding_repo = embedding_repo

    async def list(self, user_id: str) -> list[Todo]:
        return await self._repo.list_trashed(user_id)

    async def restore(self, user_id: str, todo_id: str) -> RestoredTodo | None:
        trashed = await self._repo.find_trashed(todo_id, user_id)
        if trashed is None:
            return None
        await self._repo.restore(todo_id, user_id)
        push = await auto_push_enabled(
            self._settings_repo, self._calendar_repo, user_id, trashed.calendar_id
        )
        if push:
            await self._repo.mark_for_push(todo_id, user_id)
        return RestoredTodo(trashed, push)

    async def purge(self, user_id: str, todo_id: str) -> bool:
        ids = await self._repo.purge(todo_id, user_id)
        await self._embedding_repo.delete_by_todos(ids)
        return bool(ids)

    async def purge_all(self, user_id: str | None, before: datetime | None = None) -> int:
        ids = await self._repo.purge_trashed(user_id, before)
        await self._embedding_repo.delete_by_todos(ids)
        return len(ids)
