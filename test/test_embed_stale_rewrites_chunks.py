"""회고 재임베딩 시 기존 청크를 비우는지.

GitHub #9: 재임베딩 경로가 `upsert_chunks` 만 호출했다. upsert 는 (entry_id,
chunk_index) 유니크 제약으로 **주어진 인덱스만** 갱신하므로, 회고를 편집해 단락이
4개에서 2개로 줄면 chunk_index 2,3 이 옛 본문·옛 임베딩 그대로 남는다. 삭제한
내용이 계속 주제에 매칭되고 digest 프롬프트에도 들어간다.

`delete_by_entry` 는 이미 있었지만 회고 삭제 엔드포인트에서만 불렸다.
"""
from dataclasses import dataclass
from datetime import UTC, datetime

import app.worker.tasks.embed_stale as embed_stale
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.value_objects import RetroType
from app.shared.infrastructure.config.topic import TopicConfig
from app.topic.domain.models.topic import EmbeddingQueueItem

_NOW = datetime.now(UTC)


@dataclass
class _RecordingChunkRepo:
    """delete_by_entry / upsert_chunks 의 호출 순서를 기록한다."""

    calls: list[str]

    def __init__(self, session) -> None:
        self.calls = session.chunk_calls

    async def delete_by_entry(self, entry_id: str) -> None:
        self.calls.append(f"delete:{entry_id}")

    async def upsert_chunks(self, chunks) -> None:
        self.calls.append(f"upsert:{len(chunks)}")


_MAX_DEQUEUE_CALLS = 5


class _QueueRepo:
    def __init__(self, session) -> None:
        self._session = session

    async def dequeue_batch(self, limit, user_id=None):
        self._session.dequeue_calls += 1
        if self._session.dequeue_calls > _MAX_DEQUEUE_CALLS:
            # 무한 루프를 "테스트가 멈춘다"가 아니라 "즉시 실패한다"로 바꾼다.
            raise AssertionError(
                f"dequeue 가 {_MAX_DEQUEUE_CALLS}회를 넘겼다 — _drain 이 끝나지 않는다"
            )
        return self._session.queue_items

    async def delete(self, item_id: str) -> None:
        self._session.queue_deleted.append(item_id)
        self._session.queue_items = [
            i for i in self._session.queue_items if i.id != item_id
        ]


class _EntryRepo:
    def __init__(self, session) -> None:
        self._session = session

    async def find_by_id(self, entry_id: str, user_id: str):
        return self._session.entry


class _EmbeddingService:
    def __init__(self, _config) -> None:
        pass

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 4 for _ in texts]


class _Session:
    def __init__(self, entry: JournalEntry, items: list[EmbeddingQueueItem]) -> None:
        self.entry = entry
        self.queue_items = items
        self.chunk_calls: list[str] = []
        self.queue_deleted: list[str] = []
        self.dequeue_calls = 0
        self.attempts = 0


class _Factory:
    def __init__(self, session: _Session) -> None:
        self._session = session

    def begin(self):
        session = self._session

        class _Ctx:
            async def __aenter__(self):
                return session

            async def __aexit__(self, *a):
                return False

        return _Ctx()


@dataclass(frozen=True)
class _AiConfig:
    google_api_key: str = "x"


@dataclass(frozen=True)
class _Settings:
    topic: TopicConfig
    ai: _AiConfig


def _install(monkeypatch, session: _Session) -> None:
    monkeypatch.setattr(embed_stale, "get_worker_session_factory", lambda: _Factory(session))
    monkeypatch.setattr(
        embed_stale, "get_settings", lambda: _Settings(topic=TopicConfig(), ai=_AiConfig())
    )
    monkeypatch.setattr(embed_stale, "EmbeddingService", _EmbeddingService)
    monkeypatch.setattr(embed_stale, "EmbeddingQueueRepository", _QueueRepo)
    monkeypatch.setattr(embed_stale, "EntryChunkRepository", _RecordingChunkRepo)
    monkeypatch.setattr(
        "app.retrospective.infrastructure.persistence.repositories."
        "journal_entry_repo.JournalEntryRepository",
        _EntryRepo,
    )


def _entry(content: str) -> JournalEntry:
    return JournalEntry(
        id="ent_1",
        user_id="u1",
        date_key="2026-09-09",
        title="제목",
        content=content,
        retro_type=RetroType.DAILY,
        created_at=_NOW,
    )


async def test_existing_chunks_are_cleared_before_rewriting(monkeypatch) -> None:
    """편집으로 단락이 줄어도 옛 청크가 남지 않도록, upsert 전에 지워야 한다."""
    session = _Session(
        entry=_entry("가" * 40 + "\n\n" + "나" * 40),
        items=[
            EmbeddingQueueItem(
                id="emb_q_1",
                entity_type="entry",
                entity_id="ent_1",
                user_id="u1",
                created_at=_NOW,
            )
        ],
    )
    _install(monkeypatch, session)

    await embed_stale._process_batch()

    assert session.chunk_calls == ["delete:ent_1", "upsert:2"], (
        f"delete 가 upsert 보다 먼저 와야 한다: {session.chunk_calls}"
    )
    assert session.queue_deleted == ["emb_q_1"], "처리 후 큐 항목이 지워져야 한다"


class _FailingChunkRepo:
    """upsert 가 항상 실패 — 큐 항목이 지워지지 않는 영구 실패 항목을 흉내낸다."""

    def __init__(self, session) -> None:
        self._session = session

    async def delete_by_entry(self, entry_id: str) -> None:
        pass

    async def upsert_chunks(self, chunks) -> None:
        self._session.attempts += 1
        raise RuntimeError("gemini rejected this row")


async def test_drain_terminates_when_an_item_can_never_succeed(monkeypatch) -> None:
    """영구 실패 항목이 있어도 _drain 이 끝나야 한다.

    _process_batch 가 `len(items)` 를 돌려주면 실패 항목이 매번 다시 꺼내지면서
    호출자의 while 루프가 영원히 돈다. embed_stale 은 요약 dispatcher·캘린더 sync 와
    같은 `default` 큐를 concurrency 2 로 공유하므로, 하나가 물리면 그 두 스케줄이
    통째로 멈춘다. 진척(=삭제된 큐 항목 수)을 돌려줘야 0 이 되어 종료된다.
    """
    session = _Session(
        entry=_entry("가" * 40),
        items=[
            EmbeddingQueueItem(
                id="emb_q_bad",
                entity_type="entry",
                entity_id="ent_1",
                user_id="u1",
                created_at=_NOW,
            )
        ],
    )
    _install(monkeypatch, session)
    monkeypatch.setattr(embed_stale, "EntryChunkRepository", _FailingChunkRepo)

    processed = await embed_stale._drain()

    assert processed == 0, "실패한 항목을 진척으로 세면 안 된다"
    assert session.attempts == 1, (
        f"같은 항목을 계속 다시 꺼내고 있다 — 무한 루프 (시도 {session.attempts}회)"
    )
    assert session.dequeue_calls == 1
    assert session.queue_deleted == [], "실패 항목은 재시도를 위해 큐에 남아야 한다"
