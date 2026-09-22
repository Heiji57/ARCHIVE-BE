"""async 태스크용 Celery Task 기반 클래스 — celery_aio_pool 에서 `self.request` 복원.

문제: celery_aio_pool 은 호출 스레드에서 `push_request()` 후 `task.run(*args)` 로 코루틴을
만들고, 본문은 **별도의 이벤트 루프 스레드**에서 실행한다. Celery 의 request 스택은 스레드
로컬이라 본문 안의 `self.request` 는 빈 Context(id=None, retries=0, called_directly=True)
가 된다(실측). 그 결과:
- `self.retry()` 가 called_directly 분기로 빠져 **재큐잉 없이** 원본 예외만 재발생
  → 모든 async 태스크의 재시도가 실제로는 한 번도 일어나지 않았다.
- `self.request.retries` 가 항상 0 → 백오프가 늘지 않고, 재시도 판별 로직이 오작동.

해결: `run` 을 감싸 호출 스레드(request 가 push 돼 있는 곳)에서 request 를 캡처하고, 루프
스레드의 코루틴 안에서 ContextVar 로 복원한다. asyncio Task 마다 context 가 분리되므로
동시에 도는 태스크끼리 섞이지 않는다. 같은 자리에서 로그 컨텍스트(task_id/task_name)도
바인딩해 워커 로그를 태스크 단위로 추적할 수 있게 한다.
"""
import inspect
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

import structlog
from celery import Task
from celery.app.task import Context

# (task name, request) — 다른 태스크 객체가 이 값을 자기 request 로 오인하지 않도록 이름을 함께 둔다.
_current_request: ContextVar[tuple[str, Context] | None] = ContextVar(
    "celery_current_request", default=None
)


async def _run_with_request(task_name: str, request: Context, coro: Awaitable[Any]) -> Any:
    token = _current_request.set((task_name, request))
    structlog.contextvars.bind_contextvars(task_id=request.id, task_name=task_name)
    try:
        return await coro
    finally:
        structlog.contextvars.unbind_contextvars("task_id", "task_name")
        _current_request.reset(token)


def _wrap_async_run(orig: Callable[..., Awaitable[Any]], bound: bool) -> Callable[..., Any]:
    def run(self: Task, *args: Any, **kwargs: Any) -> Awaitable[Any]:
        # 여기는 celery_aio_pool 이 run 을 "호출"하는 호출 스레드 — request 가 push 돼 있다.
        request = Task._get_request(self)
        coro = orig(self, *args, **kwargs) if bound else orig(*args, **kwargs)
        return _run_with_request(self.name, request, coro)

    run.__name__ = getattr(orig, "__name__", "run")
    run.__doc__ = orig.__doc__
    # 풀이 이 함수를 코루틴 함수로 인식해 호출 스레드에서 직접 호출하게 한다 — 일반 함수로
    # 보이면 asyncio.to_thread 로 다른 스레드에서 호출돼 request 캡처가 무의미해진다.
    return inspect.markcoroutinefunction(run)


class AsyncContextTask(Task):
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        raw = cls.__dict__.get("run")
        if raw is None:
            return
        bound = not isinstance(raw, staticmethod)
        func = raw if bound else raw.__func__
        if inspect.iscoroutinefunction(func):
            cls.run = _wrap_async_run(func, bound)  # type: ignore[method-assign]

    @property
    def request(self) -> Context:  # type: ignore[override]
        current = _current_request.get()
        if current is not None and current[0] == self.name:
            return current[1]
        return self._get_request()
