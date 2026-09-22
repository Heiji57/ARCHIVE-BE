"""`generate_digest_task` 의 AI 실패 분기.

- 예전엔 `autoretry_for=(ServerError, TimeoutException)` 에 의존했는데, celery_aio_pool 의
  async task 에서는 이 데코레이터가 작동하지 않아 재시도가 한 번도 일어나지 않았다.
  → AI 일시 장애(AIServiceUnavailable / QuotaExceeded)는 본문에서 self.retry().
- 재시도로 다시 온 실행은 직전 시도가 남긴 IN_PROGRESS 를 "중복 실행" 으로 오인해 즉시
  return 하면 안 된다 (그러면 영구 IN_PROGRESS).
- 재시도해도 같은 실패(RequestRejected / EmptyResponse)는 재시도 없이 FAILED.
- safety filter 빈 응답에 DigestNotFoundException(404 의미)을 빌려 쓰던 오용 제거.
"""
from types import SimpleNamespace

import pytest

import app.worker.tasks.generate_digest as digest_module
from app.shared.domain.exceptions.external import (
    AIEmptyResponseException,
    AIRequestRejectedException,
    AIServiceUnavailableException,
)
from app.topic.domain.models.value_objects import DigestStatus


class _Session:
    pass


class _Begin:
    async def __aenter__(self):
        return _Session()

    async def __aexit__(self, *exc):
        return False


class _Factory:
    def begin(self):
        return _Begin()


class _DigestRepo:
    def __init__(self, state: dict) -> None:
        self._state = state

    async def find_by_id(self, digest_id, user_id):
        return SimpleNamespace(status=self._state["status"])

    async def update_status(self, digest_id, status, content=None):
        self._state["status"] = status

    async def update_watermark(self, digest_id, key):
        pass


class _TopicRepo:
    def __init__(self, session) -> None:
        pass

    async def find_by_id(self, topic_id, user_id):
        return SimpleNamespace(name="topic", description=None)


class _UserRepo:
    def __init__(self, session) -> None:
        pass

    async def find_by_id(self, user_id):
        return None


class _Redis:
    def __init__(self) -> None:
        self.published: list[str] = []

    async def publish(self, channel, message):
        self.published.append(message)

    async def aclose(self):
        pass


def _embedding_raising(exc_type):
    class _Emb:
        def __init__(self, ai_settings) -> None:
            pass

        async def embed_text(self, text):
            raise exc_type("gemini")

    return _Emb


def _patch(monkeypatch, state: dict, redis: _Redis, exc_type) -> None:
    async def no_pending(user_id):
        return 0

    monkeypatch.setattr(digest_module, "get_worker_session_factory", lambda: _Factory())
    monkeypatch.setattr(digest_module, "TopicDigestRepository", lambda s: _DigestRepo(state))
    monkeypatch.setattr(digest_module, "TopicRepository", _TopicRepo)
    monkeypatch.setattr(digest_module, "UserRepository", _UserRepo)
    monkeypatch.setattr(digest_module, "_process_batch", no_pending)
    monkeypatch.setattr(digest_module, "EmbeddingService", _embedding_raising(exc_type))
    monkeypatch.setattr(digest_module.Redis, "from_url", lambda *a, **kw: redis)
    monkeypatch.setattr(digest_module, "get_exponential_backoff_interval", lambda **kw: 5)


async def test_ai_unavailable_triggers_self_retry_without_marking_failed(monkeypatch):
    state = {"status": DigestStatus.PENDING}
    redis = _Redis()
    retried: list[dict] = []

    def fake_retry(*, exc=None, countdown=None, **kw):
        retried.append({"exc": exc, "countdown": countdown})
        raise digest_module.Retry(exc=exc)

    _patch(monkeypatch, state, redis, AIServiceUnavailableException)
    monkeypatch.setattr(digest_module.generate_digest_task, "retry", fake_retry)

    with pytest.raises(digest_module.Retry):
        await digest_module.generate_digest_task.run("dig_1", "top_1", "usr_1")

    assert len(retried) == 1 and isinstance(retried[0]["exc"], AIServiceUnavailableException)
    assert state["status"] == DigestStatus.IN_PROGRESS, (
        "재시도 예약 중에 FAILED 로 확정하면 안 된다"
    )
    assert not any('"failed"' in m for m in redis.published)


async def test_retry_run_is_not_blocked_by_its_own_in_progress_status(monkeypatch):
    state = {"status": DigestStatus.IN_PROGRESS}  # 직전 시도가 남긴 상태
    redis = _Redis()
    reached_ai: list[bool] = []

    class _Emb:
        def __init__(self, ai_settings) -> None:
            pass

        async def embed_text(self, text):
            reached_ai.append(True)
            raise AIRequestRejectedException("stop here")

    _patch(monkeypatch, state, redis, AIRequestRejectedException)
    monkeypatch.setattr(digest_module, "EmbeddingService", _Emb)

    task = digest_module.generate_digest_task
    task.push_request(retries=1)
    try:
        with pytest.raises(AIRequestRejectedException):
            await task.run("dig_1", "top_1", "usr_1")
    finally:
        task.pop_request()
    assert reached_ai == [True]

    # 첫 실행(retries=0)에서 이미 IN_PROGRESS 면 진짜 중복 실행 — 그대로 막는다.
    reached_ai.clear()
    state["status"] = DigestStatus.IN_PROGRESS
    await task.run("dig_1", "top_1", "usr_1")
    assert reached_ai == []


@pytest.mark.parametrize("exc_type", [AIRequestRejectedException, AIEmptyResponseException])
async def test_non_retryable_ai_failure_marks_failed(monkeypatch, exc_type):
    state = {"status": DigestStatus.PENDING}
    redis = _Redis()
    retried: list[object] = []

    def fake_retry(**kw):
        retried.append(kw)
        raise digest_module.Retry()

    _patch(monkeypatch, state, redis, exc_type)
    monkeypatch.setattr(digest_module.generate_digest_task, "retry", fake_retry)

    with pytest.raises(exc_type):
        await digest_module.generate_digest_task.run("dig_1", "top_1", "usr_1")

    assert retried == []
    assert state["status"] == DigestStatus.FAILED
    assert any('"failed"' in m for m in redis.published)
