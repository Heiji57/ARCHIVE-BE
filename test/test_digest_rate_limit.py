"""주제 정리 생성 한도 — AI 1회 호출이 가장 비싼 경로인데 한도가 없어 연타 시 비용 상한이 없었다."""
from datetime import UTC, datetime

import pytest

import app.topic.infrastructure.cache.digest_rate_limiter as limiter_module
from app.topic.application.dtos.commands import GenerateDigestCommand
from app.topic.application.use_cases.generate_digest import GenerateDigestUseCase
from app.topic.domain.exceptions.exceptions import (
    DigestAlreadyInProgressException,
    DigestRateLimitExceededException,
)
from app.topic.domain.models.topic import Topic, TopicDigest
from app.topic.domain.models.value_objects import DigestStatus
from app.topic.infrastructure.cache.digest_rate_limiter import DigestRateLimiter

_NOW = datetime.now(UTC)


class _FakeRedis:
    """Sorted Set 명령 중 limiter 가 쓰는 것만."""

    def __init__(self) -> None:
        self.sets: dict[str, dict[str, float]] = {}

    def pipeline(self) -> "_Pipe":
        return _Pipe(self)


class _Pipe:
    def __init__(self, redis: _FakeRedis) -> None:
        self._r = redis
        self._ops: list = []

    def zremrangebyscore(self, key, lo, hi):
        self._ops.append(("zrem", key, lo, hi))

    def zcard(self, key):
        self._ops.append(("zcard", key))

    def zrange(self, key, start, end, withscores=False):
        self._ops.append(("zrange", key))

    def zadd(self, key, mapping):
        self._ops.append(("zadd", key, mapping))

    def expire(self, key, ttl):
        self._ops.append(("expire", key))

    async def execute(self):
        out = []
        for op in self._ops:
            s = self._r.sets.setdefault(op[1], {})
            if op[0] == "zrem":
                for m in [m for m, sc in s.items() if op[2] <= sc <= op[3]]:
                    del s[m]
                out.append(None)
            elif op[0] == "zcard":
                out.append(len(s))
            elif op[0] == "zrange":
                out.append(sorted(s.items(), key=lambda kv: kv[1])[:1])
            elif op[0] == "zadd":
                s.update(op[2])
                out.append(1)
            else:
                out.append(True)
        return out


async def test_limit_blocks_after_n_and_reports_retry_after(monkeypatch) -> None:
    clock = [1_000_000.0]
    monkeypatch.setattr(limiter_module.time, "time", lambda: clock[0])
    limiter = DigestRateLimiter(_FakeRedis(), limit=3, window_seconds=100)

    for _ in range(3):
        await limiter.check_and_record("usr_1")
        clock[0] += 10

    with pytest.raises(DigestRateLimitExceededException) as ei:
        await limiter.check_and_record("usr_1")
    detail = ei.value.details[0]
    assert detail["limit"] == 3 and detail["windowSeconds"] == 100
    # 가장 오래된 기록(t=1_000_000)이 창에서 빠지는 시각까지: 100 - 30 + 1
    assert detail["retryAfterSeconds"] == 71


async def test_limit_recovers_after_window_and_is_per_user(monkeypatch) -> None:
    clock = [1_000_000.0]
    monkeypatch.setattr(limiter_module.time, "time", lambda: clock[0])
    limiter = DigestRateLimiter(_FakeRedis(), limit=1, window_seconds=100)

    await limiter.check_and_record("usr_1")
    await limiter.check_and_record("usr_2")  # 다른 사용자는 독립
    with pytest.raises(DigestRateLimitExceededException):
        await limiter.check_and_record("usr_1")

    clock[0] += 101
    await limiter.check_and_record("usr_1")


# ── 유스케이스 ───────────────────────────────────────────────────


class _TopicRepo:
    async def find_by_id(self, topic_id, user_id):
        return Topic(id=topic_id, user_id=user_id, name="배포", created_at=_NOW)


class _DigestRepo:
    def __init__(self, existing: TopicDigest | None) -> None:
        self._existing = existing

    async def find_by_topic(self, topic_id, user_id):
        return self._existing

    async def update_status(self, digest_id, status, content=None):
        pass

    async def save(self, digest):
        return digest


class _CountingLimiter:
    def __init__(self, exc: Exception | None = None) -> None:
        self.calls = 0
        self._exc = exc

    async def check_and_record(self, user_id):
        self.calls += 1
        if self._exc:
            raise self._exc


def _digest(status: DigestStatus) -> TopicDigest:
    return TopicDigest(
        id="dig_1", topic_id="top_1", user_id="usr_1", status=status, created_at=_NOW
    )


async def test_in_progress_conflict_is_not_counted() -> None:
    limiter = _CountingLimiter()
    uc = GenerateDigestUseCase(
        _TopicRepo(), _DigestRepo(_digest(DigestStatus.IN_PROGRESS)), limiter  # type: ignore[arg-type]
    )
    with pytest.raises(DigestAlreadyInProgressException):
        await uc.execute(GenerateDigestCommand(user_id="usr_1", topic_id="top_1"))
    assert limiter.calls == 0


@pytest.mark.parametrize("existing", [None, _digest(DigestStatus.COMPLETED)])
async def test_enqueue_paths_are_counted(existing) -> None:
    limiter = _CountingLimiter()
    uc = GenerateDigestUseCase(_TopicRepo(), _DigestRepo(existing), limiter)  # type: ignore[arg-type]
    await uc.execute(GenerateDigestCommand(user_id="usr_1", topic_id="top_1"))
    assert limiter.calls == 1


async def test_limit_exceeded_blocks_before_state_change() -> None:
    """한도 초과면 digest 를 PENDING 으로 되돌리지 않아야 한다 — 큐에 안 들어가는데 PENDING
    으로 남으면 FE 가 영원히 '정리 중' 을 본다."""
    existing = _digest(DigestStatus.COMPLETED)
    limiter = _CountingLimiter(DigestRateLimitExceededException(10, 86400, 5))
    uc = GenerateDigestUseCase(_TopicRepo(), _DigestRepo(existing), limiter)  # type: ignore[arg-type]
    with pytest.raises(DigestRateLimitExceededException):
        await uc.execute(GenerateDigestCommand(user_id="usr_1", topic_id="top_1"))
    assert existing.status == DigestStatus.COMPLETED
