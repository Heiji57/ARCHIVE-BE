"""celery_aio_pool 에서 async 태스크 본문이 `self.request` 를 보고, `self.retry()` 가 실제로
재큐잉하는지 — 실제 풀(AsyncIOPool.run_in_pool)을 태워 검증한다.

실측된 원래 증상: 풀은 호출 스레드에서 push_request 후 코루틴 본문을 별도 루프 스레드에서
실행하는데, request 스택이 스레드 로컬이라 본문의 self.request 가 빈 Context
(id=None, retries=0, called_directly=True) 였다. Task.retry() 는 called_directly 면 재큐잉
없이 원본 예외만 재발생 → 모든 async 태스크 재시도가 실제로는 한 번도 일어나지 않았다.
기존 재시도 테스트들은 `retry` 를 목으로 갈아 끼워 이 경로를 검증하지 못했다.
"""
import celery.canvas as canvas
import pytest
from celery import Celery
from celery.exceptions import Retry
from celery_aio_pool.pool import AsyncIOPool

from app.worker.task_base import AsyncContextTask


@pytest.fixture
def probe_app():
    return Celery(
        "probe", broker="memory://", backend="cache+memory://", task_cls=AsyncContextTask
    )


def _run_like_aio_tracer(task, *args):
    """celery_aio_pool tracer 와 같은 순서: 호출 스레드에서 push → 풀에서 실행 → pop."""
    task.push_request(
        id="task-1", retries=2, called_directly=False, delivery_info={}, args=args, kwargs={}
    )
    try:
        return AsyncIOPool.run_in_pool(task.run, *args)
    finally:
        task.pop_request()


def test_body_sees_the_real_request(probe_app):
    seen: dict = {}

    @probe_app.task(bind=True, name="probe.seen")
    async def probe(self):
        seen.update(
            id=self.request.id,
            retries=self.request.retries,
            called_directly=self.request.called_directly,
        )

    _run_like_aio_tracer(probe_app.tasks["probe.seen"])
    assert seen == {"id": "task-1", "retries": 2, "called_directly": False}


def test_self_retry_actually_requeues(probe_app, monkeypatch):
    queued: list = []
    monkeypatch.setattr(
        canvas.Signature,
        "apply_async",
        lambda self, *a, **kw: queued.append((self.task, self.args, self.options)),
    )

    @probe_app.task(bind=True, name="probe.retry", max_retries=5)
    async def probe(self, x):
        raise self.retry(exc=ValueError("transient"), countdown=3)

    with pytest.raises(Retry):
        _run_like_aio_tracer(probe_app.tasks["probe.retry"], 7)
    assert len(queued) == 1, "재큐잉 없이 원본 예외만 재발생하던 회귀"
    task_name, args, options = queued[0]
    assert (task_name, args, options["countdown"]) == ("probe.retry", (7,), 3)


def test_unbound_async_task_still_runs(probe_app):
    @probe_app.task(name="probe.unbound")
    async def double(y):
        return y * 2

    assert _run_like_aio_tracer(probe_app.tasks["probe.unbound"], 21) == 42


def test_project_celery_app_uses_the_context_task():
    from app.worker.tasks.generate_digest import generate_digest_task
    from app.worker.tasks.generate_summary import generate_summary_task
    from app.worker.tasks.push_calendars import delete_calendar_event_task

    for task in (generate_summary_task, generate_digest_task, delete_calendar_event_task):
        assert isinstance(task, AsyncContextTask), task.name


def test_concurrent_tasks_in_one_loop_keep_their_own_request(probe_app):
    """풀의 이벤트 루프 하나에서 두 태스크가 번갈아 실행돼도 서로의 request 를 보지 않는다."""
    import asyncio
    import threading

    seen: dict[str, list[str]] = {}
    both_started = threading.Barrier(2)

    @probe_app.task(bind=True, name="probe.concurrent")
    async def probe(self, label):
        before = self.request.id
        await asyncio.sleep(0.05)  # 다른 태스크가 이 사이에 실행된다
        seen[label] = [before, self.request.id]

    task = probe_app.tasks["probe.concurrent"]

    def run(label: str) -> None:
        task.push_request(id=f"id-{label}", retries=0, called_directly=False, args=(label,))
        try:
            both_started.wait()
            AsyncIOPool.run_in_pool(task.run, label)
        finally:
            task.pop_request()

    threads = [threading.Thread(target=run, args=(label,)) for label in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert seen == {"a": ["id-a", "id-a"], "b": ["id-b", "id-b"]}
