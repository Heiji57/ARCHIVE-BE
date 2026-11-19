"""휴지통 — 할 일·회고 모듈의 휴지통을 모아 보여 주고 종류별로 넘긴다.

각 모듈이 자기 테이블을 다루고(`TodoTrashUseCase`, `EntryTrashUseCase`), 여기는 목록 합치기와
라우팅만 한다(12 §1).
"""

from dataclasses import dataclass
from datetime import datetime

from app.data.domain.exceptions.exceptions import (
    TrashItemNotFoundException,
    TrashKindInvalidException,
)
from app.data.domain.models.trash import TRASH_KINDS, TrashItem, TrashKind
from app.retrospective.application.use_cases.entry_trash import EntryTrashUseCase
from app.todo.application.use_cases.trash import TodoTrashUseCase


@dataclass(frozen=True)
class RestoreOutcome:
    kind: TrashKind
    id: str
    push_todo_id: str | None = None  # 다시 Google 로 보낼 할 일
    reembed_todo_id: str | None = None  # 임베딩을 다시 만들 할 일(시리즈 base 제외)


def check_kind(kind: str) -> TrashKind:
    if kind not in TRASH_KINDS:
        raise TrashKindInvalidException(f"kind must be one of {list(TRASH_KINDS)}")
    return kind


class TrashUseCase:
    def __init__(self, todos: TodoTrashUseCase, entries: EntryTrashUseCase) -> None:
        self._todos = todos
        self._entries = entries

    async def list(
        self, user_id: str, kind: str | None, page: int, size: int
    ) -> tuple[list[TrashItem], int]:
        """지운 시각 내림차순. 휴지통은 30일치뿐이라 합친 뒤 메모리에서 자른다."""
        kinds = (check_kind(kind),) if kind else TRASH_KINDS
        items: list[TrashItem] = []
        if "todo" in kinds:
            items += [
                TrashItem("todo", t.id, t.title, t.date_key, t.deleted_at)
                for t in await self._todos.list(user_id)
                if t.deleted_at is not None
            ]
        if "entry" in kinds:
            items += [
                TrashItem("entry", e.id, e.title, e.date_key, e.deleted_at)
                for e in await self._entries.list(user_id)
                if e.deleted_at is not None
            ]
        items.sort(key=lambda i: i.deleted_at, reverse=True)
        start = (page - 1) * size
        return items[start : start + size], len(items)

    async def restore(self, user_id: str, kind: str, item_id: str) -> RestoreOutcome:
        kind = check_kind(kind)
        if kind == "todo":
            restored = await self._todos.restore(user_id, item_id)
            if restored is None:
                raise TrashItemNotFoundException()
            return RestoreOutcome(
                "todo",
                item_id,
                push_todo_id=item_id if restored.push else None,
                reembed_todo_id=None if restored.todo.is_series_base else item_id,
            )
        if await self._entries.restore(user_id, item_id) is None:
            raise TrashItemNotFoundException()
        return RestoreOutcome("entry", item_id)

    async def purge(self, user_id: str, kind: str, item_id: str) -> None:
        kind = check_kind(kind)
        found = (
            await self._todos.purge(user_id, item_id)
            if kind == "todo"
            else await self._entries.purge(user_id, item_id)
        )
        if not found:
            raise TrashItemNotFoundException()

    async def empty(self, user_id: str) -> int:
        return await self._todos.purge_all(user_id) + await self._entries.purge_all(user_id)

    async def purge_expired(self, before: datetime) -> int:
        """worker.purge_trash — 모든 사용자의 before 이전에 지운 것."""
        return await self._todos.purge_all(None, before) + await self._entries.purge_all(
            None, before
        )
