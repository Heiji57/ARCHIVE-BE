"""digest 증분 재생성 + 앞뒤 청크 문맥 보강.

- 매칭 청크(단락)만 프롬프트에 넣으면 같은 회고의 앞뒤 맥락이 잘려 정보가 유실됐다
  → 같은 회고의 인접 청크를 붙인다.
- 재생성마다 주제 전체를 다시 읽으면 비용이 회고 누적량에 비례한다
  → 안전할 때만 "이전 본문 + 새 청크" 병합, 나머지는 전체 재생성.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.topic.infrastructure.ai.gemini_client as gemini_module
import app.worker.tasks.generate_digest as digest_module
from app.shared.infrastructure.config.topic import TopicConfig
from app.topic.domain.models.topic import SimilarChunk, TopicDigest
from app.topic.domain.models.value_objects import DigestStatus
from app.worker.tasks.generate_digest import (
    _build_prompt,
    _fingerprint,
    _static_full_reason,
    _with_neighbors,
)

_T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
_FP = "fp"


def _chunk(entry_id: str, idx: int, text: str = "", date_key: str = "2026-09-01") -> SimilarChunk:
    return SimilarChunk(
        id=f"c_{entry_id}_{idx}",
        entry_id=entry_id,
        chunk_index=idx,
        text=text or f"{entry_id}-{idx}",
        date_key=date_key,
    )


def _digest(**kw) -> TopicDigest:
    base: dict = dict(
        id="dig_1",
        topic_id="top_1",
        user_id="usr_1",
        status=DigestStatus.PENDING,
        content="# 기존 정리",
        last_generated_at=_T0,
        incremental_count=0,
        full_fingerprint=_FP,
        source_entry_ids=["e_old"],
        created_at=_T0,
    )
    base.update(kw)
    return TopicDigest(**base)


# ── 전체 재생성 판정 ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"content": None}, "initial"),
        ({"last_generated_at": None}, "initial"),
        ({"full_fingerprint": "other"}, "fingerprint_changed"),
        ({"full_fingerprint": None}, "fingerprint_changed"),
        ({"incremental_count": 5}, "periodic_reset"),
        ({"incremental_count": 4}, None),
    ],
)
def test_static_full_reason(overrides, expected) -> None:
    assert _static_full_reason(_digest(**overrides), _FP, full_regen_every=5) == expected


def test_fingerprint_changes_with_topic_and_settings() -> None:
    cfg = TopicConfig()
    base = _fingerprint("배포", "자동화", "gemini-x", cfg)
    assert base == _fingerprint("배포", "자동화", "gemini-x", cfg)
    assert base != _fingerprint("배포", "수동", "gemini-x", cfg)
    assert base != _fingerprint("배포", "자동화", "gemini-y", cfg)
    assert base != _fingerprint(
        "배포", "자동화", "gemini-x", TopicConfig(topic_similarity_threshold=0.7)
    )


# ── 앞뒤 청크 보강 ────────────────────────────────────────────────


class _NeighborRepo:
    def __init__(self) -> None:
        self.requested: list[tuple[str, int]] | None = None

    async def find_by_entry_indices(self, user_id, keys):
        self.requested = keys
        return [_chunk(e, i) for e, i in keys]


async def test_with_neighbors_requests_adjacent_missing_chunks_only() -> None:
    repo = _NeighborRepo()
    chunks = [_chunk("e_a", 0), _chunk("e_a", 1), _chunk("e_b", 3)]
    result = await _with_neighbors(repo, "usr_1", chunks, window=1)  # type: ignore[arg-type]

    # e_a: -1 은 없음, 0·1 은 이미 있음 → 2 만. e_b: 2, 4.
    assert repo.requested == [("e_a", 2), ("e_b", 2), ("e_b", 4)]
    assert len(result) == 6


async def test_with_neighbors_window_zero_is_noop() -> None:
    repo = _NeighborRepo()
    chunks = [_chunk("e_a", 1)]
    assert await _with_neighbors(repo, "usr_1", chunks, window=0) == chunks  # type: ignore[arg-type]
    assert repo.requested is None


# ── 프롬프트 ─────────────────────────────────────────────────────


async def test_prompt_merges_neighbors_in_order_without_duplicates() -> None:
    chunks = [
        _chunk("e_a", 1, "매칭 단락"),
        _chunk("e_a", 0, "앞 단락"),
        _chunk("e_a", 2, "뒤 단락"),
        _chunk("e_a", 1, "매칭 단락"),
    ]
    prompt = await _build_prompt("배포", "", chunks, [])
    assert prompt.count("매칭 단락") == 1
    assert prompt.index("앞 단락") < prompt.index("매칭 단락") < prompt.index("뒤 단락")


async def test_incremental_prompt_carries_existing_digest() -> None:
    prompt = await _build_prompt(
        "배포", "", [_chunk("e_new", 0, "새 회고")], [], previous_content="# 기존 정리"
    )
    assert "### Existing Digest" in prompt and "# 기존 정리" in prompt
    assert "### New Journal Entry Excerpts" in prompt
    assert prompt.index("# 기존 정리") < prompt.index("새 회고")
    assert "Preserve every fact in the existing digest" in prompt


async def test_full_prompt_has_no_existing_digest_section() -> None:
    prompt = await _build_prompt("배포", "", [_chunk("e_a", 0)], [])
    assert "Existing Digest" not in prompt


# ── 워커 흐름 ────────────────────────────────────────────────────


class _Begin:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


class _Factory:
    def begin(self):
        return _Begin()


class _Redis:
    async def publish(self, channel, message):
        pass

    async def aclose(self):
        pass


def _run_worker(monkeypatch, digest: TopicDigest, *, changed: list[str], new_chunks, all_chunks):
    calls: dict = {"searches": [], "completed": None, "prompt": None}

    class _DigestRepo:
        def __init__(self, session) -> None:
            pass

        async def find_by_id(self, digest_id, user_id):
            return digest

        async def update_status(self, digest_id, status, content=None):
            pass

        async def complete_generation(self, digest_id, **kw):
            calls["completed"] = kw

    class _ChunkRepo:
        def __init__(self, session) -> None:
            pass

        async def find_changed_entry_ids(self, user_id, entry_ids, since):
            return changed

        async def search_similar(self, **kw):
            calls["searches"].append(kw.get("created_after"))
            return new_chunks if kw.get("created_after") else all_chunks

        async def find_by_entry_indices(self, user_id, keys):
            return []

    class _TodoRepo:
        def __init__(self, session) -> None:
            pass

        async def search_similar(self, **kw):
            return []

    class _Emb:
        def __init__(self, ai) -> None:
            pass

        async def embed_text(self, text):
            return [0.0]

    class _Gemini:
        def __init__(self, ai) -> None:
            pass

        async def generate(self, prompt):
            calls["prompt"] = prompt
            return "# 새 정리"

    class _Topic:
        def __init__(self, session) -> None:
            pass

        async def find_by_id(self, topic_id, user_id):
            return SimpleNamespace(name="배포", description="")

    class _User:
        def __init__(self, session) -> None:
            pass

        async def find_by_id(self, user_id):
            return None

    async def no_pending(user_id):
        return 0

    monkeypatch.setattr(digest_module, "get_worker_session_factory", lambda: _Factory())
    monkeypatch.setattr(digest_module, "TopicDigestRepository", _DigestRepo)
    monkeypatch.setattr(digest_module, "EntryChunkRepository", _ChunkRepo)
    monkeypatch.setattr(digest_module, "TodoEmbeddingRepository", _TodoRepo)
    monkeypatch.setattr(digest_module, "TopicRepository", _Topic)
    monkeypatch.setattr(digest_module, "UserRepository", _User)
    monkeypatch.setattr(digest_module, "EmbeddingService", _Emb)
    monkeypatch.setattr(digest_module, "_process_batch", no_pending)
    monkeypatch.setattr(digest_module.Redis, "from_url", lambda *a, **kw: _Redis())
    monkeypatch.setattr(gemini_module, "TopicGeminiClient", _Gemini)
    # 기존 digest 의 fingerprint 가 현재 설정과 일치하도록 맞춘다.
    monkeypatch.setattr(digest_module, "_fingerprint", lambda *a: _FP)
    return calls


async def test_incremental_merges_new_chunks_into_existing_digest(monkeypatch) -> None:
    digest = _digest(incremental_count=2)
    calls = _run_worker(
        monkeypatch,
        digest,
        changed=[],
        new_chunks=[_chunk("e_new", 0, "새 회고")],
        all_chunks=[_chunk("e_old", 0)],
    )
    await digest_module.generate_digest_task.run("dig_1", "top_1", "usr_1")

    assert calls["searches"] == [_T0], "증분은 마지막 생성 이후 청크만 읽어야 한다"
    assert "# 기존 정리" in calls["prompt"] and "새 회고" in calls["prompt"]
    done = calls["completed"]
    assert done["incremental_count"] == 3
    assert done["source_entry_ids"] == ["e_old", "e_new"]
    assert done["content"] == "# 새 정리"
    assert done["generated_at"] > _T0


async def test_changed_past_entry_forces_full(monkeypatch) -> None:
    calls = _run_worker(
        monkeypatch,
        _digest(incremental_count=2),
        changed=["e_old"],
        new_chunks=[_chunk("e_new", 0)],
        all_chunks=[_chunk("e_old", 0), _chunk("e_new", 0)],
    )
    await digest_module.generate_digest_task.run("dig_1", "top_1", "usr_1")

    assert calls["searches"] == [None], "과거 회고 수정 시 증분 검색 없이 전체를 읽어야 한다"
    assert "Existing Digest" not in calls["prompt"]
    assert calls["completed"]["incremental_count"] == 0
    assert calls["completed"]["source_entry_ids"] == ["e_old", "e_new"]


async def test_no_new_sources_forces_full(monkeypatch) -> None:
    calls = _run_worker(
        monkeypatch,
        _digest(incremental_count=1),
        changed=[],
        new_chunks=[],
        all_chunks=[_chunk("e_old", 0)],
    )
    await digest_module.generate_digest_task.run("dig_1", "top_1", "usr_1")

    assert calls["searches"] == [_T0, None]
    assert "Existing Digest" not in calls["prompt"]
    assert calls["completed"]["incremental_count"] == 0


async def test_first_generation_is_full(monkeypatch) -> None:
    calls = _run_worker(
        monkeypatch,
        _digest(content=None, last_generated_at=None, full_fingerprint=None, source_entry_ids=[]),
        changed=[],
        new_chunks=[],
        all_chunks=[_chunk("e_a", 0)],
    )
    await digest_module.generate_digest_task.run("dig_1", "top_1", "usr_1")

    assert calls["searches"] == [None]
    assert calls["completed"]["source_entry_ids"] == ["e_a"]
    assert calls["completed"]["generated_at"] > _T0 - timedelta(days=1)
