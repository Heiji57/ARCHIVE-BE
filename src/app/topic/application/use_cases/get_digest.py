from dataclasses import dataclass

from app.retrospective.domain.repositories.repository import IJournalEntryRepository
from app.todo.domain.repositories.repository import ITodoRepository
from app.topic.application.dtos.queries import GetDigestByIdQuery, GetDigestQuery
from app.topic.domain.exceptions.exceptions import DigestNotFoundException, TopicNotFoundException
from app.topic.domain.models.topic import TopicDigest
from app.topic.domain.repositories.repository import ITopicDigestRepository, ITopicRepository


@dataclass(frozen=True)
class DigestSource:
    """구조화 정리가 가리키는 근거의 **지금** 정보 — 하루 카드의 근거 이름·종류·상태."""

    kind: str  # "entry" | "todo"
    title: str
    date_key: str
    retro_type: str | None = None  # entry 만
    status: str | None = None  # todo 만 — 정리 시점이 아니라 현재 상태


class GetDigestUseCase:
    def __init__(
        self,
        topic_repo: ITopicRepository,
        digest_repo: ITopicDigestRepository,
        entry_repo: IJournalEntryRepository,
        todo_repo: ITodoRepository,
    ) -> None:
        self._topic_repo = topic_repo
        self._digest_repo = digest_repo
        self._entry_repo = entry_repo
        self._todo_repo = todo_repo

    async def execute(self, query: GetDigestQuery) -> TopicDigest:
        topic = await self._topic_repo.find_by_id(query.topic_id, query.user_id)
        if topic is None:
            raise TopicNotFoundException()

        digest = await self._digest_repo.find_by_topic(query.topic_id, query.user_id)
        if digest is None:
            raise DigestNotFoundException()
        return digest

    async def execute_by_id(self, query: GetDigestByIdQuery) -> TopicDigest:
        digest = await self._digest_repo.find_by_id(query.digest_id, query.user_id)
        if digest is None:
            raise DigestNotFoundException()
        return digest

    async def resolve_sources(self, digest: TopicDigest) -> dict[str, DigestSource]:
        """`structured` 가 가리키는 근거만 id → 현재 정보로. 지운 근거는 빠진다(FE 가 흐리게)."""
        if digest.structured is None:
            return {}
        refs = digest.structured.source_ids()
        entry_ids = sorted(i for k, i in refs if k == "entry")
        todo_ids = sorted(i for k, i in refs if k == "todo")
        sources: dict[str, DigestSource] = {}
        if entry_ids:
            for e in await self._entry_repo.find_meta_by_ids(digest.user_id, entry_ids):
                sources[e.id] = DigestSource(
                    kind="entry",
                    title=e.title,
                    date_key=e.date_key,
                    retro_type=e.retro_type.value,
                )
        if todo_ids:
            for t in await self._todo_repo.find_meta_by_ids(digest.user_id, todo_ids):
                sources[t.id] = DigestSource(
                    kind="todo", title=t.title, date_key=t.date_key, status=t.status.value
                )
        return sources
