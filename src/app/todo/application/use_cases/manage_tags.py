"""태그 관리 — 목록(사용 수·색·순서), 이름 바꾸기·합치기, 색, 순서, 삭제.

태그 자체는 `todos.tags` 배열이 원본이다. `user_tags` 는 색·순서만 든 보조 테이블이라
이름을 바꾸거나 지우면 두 곳을 한 트랜잭션에서 함께 고친다. 태그가 바뀐 할 일은 임베딩을
다시 만들도록 큐에 넣는다(주제 매칭이 태그를 본다).
"""

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from app.shared.domain.utils.id import generate_id
from app.shared.domain.utils.unset import UNSET, _Unset
from app.todo.domain.exceptions.exceptions import TagNotFoundException
from app.todo.domain.models.user_tag import TagSummary, UserTag
from app.todo.domain.repositories.repository import ITodoRepository, IUserTagRepository
from app.topic.domain.repositories.repository import IEmbeddingQueueRepository


class ListTagsUseCase:
    def __init__(self, todo_repo: ITodoRepository, tag_repo: IUserTagRepository) -> None:
        self._todo_repo = todo_repo
        self._tag_repo = tag_repo

    async def execute(self, user_id: str) -> list[TagSummary]:
        """사용 중인 태그 + 색·순서만 저장된 태그. 순서: sort_order(있으면) → 사용 수 → 이름."""
        counts = await self._todo_repo.tag_counts(user_id)
        meta = {t.name: t for t in await self._tag_repo.list_by_user(user_id)}
        names = set(counts) | set(meta)
        summaries = [
            TagSummary(
                name=name,
                count=counts.get(name, 0),
                color=meta[name].color if name in meta else None,
                sort_order=meta[name].sort_order if name in meta else None,
            )
            for name in names
        ]
        summaries.sort(key=lambda t: (t.sort_order is None, t.sort_order or 0, -t.count, t.name))
        return summaries


@dataclass(frozen=True)
class UpdateTagCommand:
    user_id: str
    name: str
    new_name: str | _Unset = UNSET
    color: str | None | _Unset = UNSET
    sort_order: int | None | _Unset = UNSET


class UpdateTagUseCase:
    def __init__(
        self,
        todo_repo: ITodoRepository,
        tag_repo: IUserTagRepository,
        queue_repo: IEmbeddingQueueRepository,
    ) -> None:
        self._todo_repo = todo_repo
        self._tag_repo = tag_repo
        self._queue_repo = queue_repo

    async def execute(self, cmd: UpdateTagCommand) -> TagSummary:
        counts = await self._todo_repo.tag_counts(cmd.user_id)
        tag = await self._tag_repo.find_by_name(cmd.user_id, cmd.name)
        if tag is None and cmd.name not in counts:
            raise TagNotFoundException()
        tag = tag or UserTag(
            id=generate_id("tag"),
            user_id=cmd.user_id,
            name=cmd.name,
            created_at=datetime.now(UTC),
        )

        name = cmd.name
        if not isinstance(cmd.new_name, _Unset) and cmd.new_name != cmd.name:
            name = cmd.new_name
            changed = await self._todo_repo.replace_tag(cmd.user_id, cmd.name, name)
            await _requeue(self._queue_repo, cmd.user_id, changed)
            # 이미 있는 이름으로 바꾸면 합친다 — 대상 쪽 색·순서가 남는다(없으면 원래 것).
            target = await self._tag_repo.find_by_name(cmd.user_id, name)
            await self._tag_repo.delete_by_name(cmd.user_id, cmd.name)
            tag = replace(
                target or replace(tag, id=generate_id("tag")),
                name=name,
                color=(target.color if target and target.color else tag.color),
                sort_order=(
                    target.sort_order
                    if target and target.sort_order is not None
                    else tag.sort_order
                ),
            )

        if not isinstance(cmd.color, _Unset):
            tag = replace(tag, color=cmd.color)
        if not isinstance(cmd.sort_order, _Unset):
            tag = replace(tag, sort_order=cmd.sort_order)
        saved = await self._tag_repo.save(tag)

        counts = await self._todo_repo.tag_counts(cmd.user_id)
        return TagSummary(
            name=saved.name,
            count=counts.get(name, 0),
            color=saved.color,
            sort_order=saved.sort_order,
        )


class DeleteTagUseCase:
    def __init__(
        self,
        todo_repo: ITodoRepository,
        tag_repo: IUserTagRepository,
        queue_repo: IEmbeddingQueueRepository,
    ) -> None:
        self._todo_repo = todo_repo
        self._tag_repo = tag_repo
        self._queue_repo = queue_repo

    async def execute(self, user_id: str, name: str) -> None:
        """모든 할 일에서 그 태그를 뺀다. 할 일은 지우지 않는다."""
        tag = await self._tag_repo.find_by_name(user_id, name)
        changed = await self._todo_repo.replace_tag(user_id, name, None)
        if tag is None and not changed:
            raise TagNotFoundException()
        await self._tag_repo.delete_by_name(user_id, name)
        await _requeue(self._queue_repo, user_id, changed)


class ReorderTagsUseCase:
    def __init__(self, tag_repo: IUserTagRepository) -> None:
        self._tag_repo = tag_repo

    async def execute(self, user_id: str, names: list[str]) -> None:
        """names 순서대로 sort_order 0, 1, 2… — 없는 행은 만든다.

        목록에 없는 태그는 순서를 비운다.
        """
        existing = {t.name: t for t in await self._tag_repo.list_by_user(user_id)}
        now = datetime.now(UTC)
        for index, name in enumerate(names):
            tag = existing.pop(name, None) or UserTag(
                id=generate_id("tag"), user_id=user_id, name=name, created_at=now
            )
            await self._tag_repo.save(replace(tag, sort_order=index))
        for leftover in existing.values():
            if leftover.sort_order is not None:
                await self._tag_repo.save(replace(leftover, sort_order=None))


async def _requeue(
    queue_repo: IEmbeddingQueueRepository, user_id: str, todo_ids: list[str]
) -> None:
    for todo_id in todo_ids:
        await queue_repo.enqueue("todo", todo_id, user_id)
