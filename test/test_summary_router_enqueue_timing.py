"""`POST /summaries/generate` 가 AI task 를 use case 실행 직후가 아니라 응답 처리
마지막 단계(BackgroundTasks)로 미뤄 enqueue 하는지.

`generate_summary` 핸들러는 use case 실행 후 요약이 PENDING 상태일 때만
`BackgroundTasks.add_task` 로 `generate_summary_task.apply_async` 를 예약해야
한다 — use case 안에서 바로 호출하는 것보다 커밋 시점에 더 가깝게 미뤄 레이스
윈도우를 줄인다. 단, 이 스택(dishka ContainerMiddleware + Starlette)에서는
BackgroundTasks 도 요청 스코프 DB 세션 커밋보다 먼저 실행되므로 "커밋 이후 실행"을
이 메커니즘만으로 보장하지는 못한다 — 실제 정합성 보장은 워커 쪽
`SummaryRowNotYetVisibleError` 재시도가 담당한다
(`test/test_generate_summary_retries_on_not_yet_visible_row.py`). 이미 COMPLETED 인
요약을 그대로 반환하는 경로(재생성 아님)에서는 AI 를 다시 호출할 필요가 없으므로
enqueue 하면 안 된다.
"""
from datetime import UTC, date, datetime

from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import SummaryStatus, SummaryType
from app.retrospective.presentation.summary_router import generate_summary
from app.shared.domain.context.user_context import UserContext

_NOW = datetime.now(UTC)


class _FakeBackgroundTasks:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def add_task(self, func, *args, **kwargs) -> None:
        self.calls.append((func, args, kwargs))


class _StubUseCase:
    def __init__(self, result: RetroSummary) -> None:
        self._result = result

    async def execute(self, cmd):
        return self._result


def _summary(status: SummaryStatus) -> RetroSummary:
    return RetroSummary(
        id="summ_1",
        user_id="usr_1",
        summary_type=SummaryType.MONTHLY,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        status=status,
        content=None,
        created_at=_NOW,
    )


async def test_pending_result_schedules_task_via_background_tasks() -> None:
    background_tasks = _FakeBackgroundTasks()
    use_case = _StubUseCase(_summary(SummaryStatus.PENDING))

    await generate_summary(
        use_case=use_case,
        background_tasks=background_tasks,
        current_user=UserContext(id="usr_1", email="test@example.com"),
        summary_type="monthly",
        period_start="2026-08-01",
        force=False,
    )

    assert len(background_tasks.calls) == 1
    func, args, kwargs = background_tasks.calls[0]
    assert func.__name__ == "apply_async" or hasattr(func, "__self__")
    assert kwargs["args"] == ["summ_1", "usr_1"]
    assert kwargs["queue"] == "ai_tasks"
    assert kwargs["priority"] == 9


async def test_already_completed_result_does_not_schedule_task() -> None:
    background_tasks = _FakeBackgroundTasks()
    use_case = _StubUseCase(_summary(SummaryStatus.COMPLETED))

    await generate_summary(
        use_case=use_case,
        background_tasks=background_tasks,
        current_user=UserContext(id="usr_1", email="test@example.com"),
        summary_type="monthly",
        period_start="2026-08-01",
        force=False,
    )

    assert background_tasks.calls == [], "이미 완료된 요약을 반환할 땐 AI 재호출 불필요"
