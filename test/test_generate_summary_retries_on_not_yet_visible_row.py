"""`generate_summary_task` 가 아직 커밋 전이라 안 보이는 summary row 를 만나면
조용히 스킵하거나 (구버전) `autoretry_for` 에 기대지 않고, `self.retry()` 를
직접 호출해 재시도를 트리거하는지.

레이스 컨디션 수정의 실제 정합성 보장은 이 재시도가 담당한다 — 라우터가
`BackgroundTasks` 로 enqueue 시점을 커밋에 가깝게 미뤄도(`summary_router.py`), 이
스택(dishka `ContainerMiddleware` + Starlette)에서는 BackgroundTasks 조차 요청
스코프 DB 세션 커밋보다 먼저 실행되므로 "커밋 이후 실행"을 프레임워크만으로
보장할 수 없다(`test_summary_router_enqueue_timing.py` 참고).

처음엔 `SummaryRowNotYetVisibleError` 를 그냥 던지고 `autoretry_for` 에 등록해
Celery 가 알아서 재시도하게 했는데, 이 프로젝트의 실제 워커 풀
`celery_aio_pool.AsyncIOPool` 에서는 `async def` task 에 대해 `autoretry_for` 가
실제로 작동하지 않는다 — `add_autoretry_behaviour` 가 감싸는 `try/except` 는
`task._orig_run(...)` "호출"(코루틴 생성)만 감싸고, 실제 실행은 풀이 재귀 호출로
별도 수행하기 때문에 본문에서 던진 예외가 그 try/except 를 완전히 비껴간다(설치된
`celery/app/autoretry.py`, `celery_aio_pool/pool.py` 소스로 직접 확인). 그래서
`find_by_id is None` 인 지점에서 `self.retry(exc=..., countdown=...)` 를 직접
호출한다 — `Task.retry()` 는 `Retry` 를 던지기 전에 `S.apply_async()` 로 재큐잉을
동기적으로 수행하므로 이 우회 문제와 무관하게 항상 실제로 재시도된다.

이 테스트는 `self.retry` 자체를 monkeypatch 해서 "정확히 이 예외/countdown 으로
호출됐는지"를 검증한다 — `.run()` 을 직접 호출해 코루틴만 실행하고 끝나는 이전
버전의 테스트는(이 파일의 이전 리비전) `autoretry_for` 등록 여부와 무관하게
똑같이 통과했을 것이라 재시도 트리거 자체를 증명하지 못했다는 지적을 받았다.
"""
from celery.exceptions import Retry

import app.worker.tasks.generate_summary as generate_summary_module
from app.worker.tasks.generate_summary import SummaryRowNotYetVisibleError


class _RetryTriggeredError(Exception):
    """가짜 `self.retry()` 가 호출됐음을 알리는 테스트 전용 마커."""


class _FakeSummaryRepo:
    async def find_by_id(self, summary_id: str, user_id: str):
        return None


class _FakeSessionCtx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


class _FakeFactory:
    def begin(self) -> _FakeSessionCtx:
        return _FakeSessionCtx()


class _FakeRedis:
    async def publish(self, channel: str, message: str) -> None:
        return None

    async def aclose(self) -> None:
        return None


async def test_missing_row_calls_self_retry_with_expected_exc_and_countdown(
    monkeypatch,
) -> None:
    calls: list[dict] = []

    def fake_retry(*, exc=None, countdown=None, **kwargs):
        calls.append({"exc": exc, "countdown": countdown})
        raise _RetryTriggeredError()

    monkeypatch.setattr(
        generate_summary_module, "get_worker_session_factory", lambda: _FakeFactory()
    )
    monkeypatch.setattr(
        generate_summary_module,
        "RetroSummaryRepository",
        lambda session: _FakeSummaryRepo(),
    )
    monkeypatch.setattr(
        generate_summary_module.Redis, "from_url", lambda *a, **kw: _FakeRedis()
    )
    monkeypatch.setattr(generate_summary_module.generate_summary_task, "retry", fake_retry)

    raised = False
    try:
        await generate_summary_module.generate_summary_task.run("summ_missing", "usr_1")
    except _RetryTriggeredError:
        raised = True

    assert raised, "find_by_id 가 None 이면 self.retry() 를 직접 호출해야 한다"
    assert len(calls) == 1
    assert isinstance(calls[0]["exc"], SummaryRowNotYetVisibleError)
    assert (
        calls[0]["countdown"]
        == generate_summary_module._NOT_YET_VISIBLE_RETRY_COUNTDOWN_SECONDS
    )


async def test_retry_in_progress_skips_failed_marking_and_notification(
    monkeypatch,
) -> None:
    """실제 `Task.retry()` 처럼 `Retry` 를 던지는 경우, FAILED 마킹/알림 없이
    그대로 전파돼야 한다 (`except Retry: raise` 가드 회귀 방지)."""
    published: list[tuple[str, str]] = []

    class _TrackingRedis(_FakeRedis):
        async def publish(self, channel: str, message: str) -> None:
            published.append((channel, message))

    def fake_retry(*, exc=None, countdown=None, **kwargs):
        raise Retry(exc=exc)

    monkeypatch.setattr(
        generate_summary_module, "get_worker_session_factory", lambda: _FakeFactory()
    )
    monkeypatch.setattr(
        generate_summary_module,
        "RetroSummaryRepository",
        lambda session: _FakeSummaryRepo(),
    )
    monkeypatch.setattr(
        generate_summary_module.Redis, "from_url", lambda *a, **kw: _TrackingRedis()
    )
    monkeypatch.setattr(generate_summary_module.generate_summary_task, "retry", fake_retry)

    raised_type: type[BaseException] | None = None
    try:
        await generate_summary_module.generate_summary_task.run("summ_missing", "usr_1")
    except Exception as exc:
        raised_type = type(exc)

    assert raised_type is Retry, "재시도 중엔 Retry 가 그대로 전파돼야 한다(FAILED 마킹 우회)"
    assert published == [], "재시도 중엔 실패 상태/알림을 publish 하면 안 된다"
