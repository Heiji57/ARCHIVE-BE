"""RequestSummaryUseCase 가 celery task 를 직접 enqueue 하지 않는지.

이전엔 use case 안에서 `generate_summary_task.apply_async(...)` 를 바로 호출했는데,
이 시점은 요청 스코프 DB 세션이 아직 커밋되기 전이다(`SharedProvider.db_session` 의
`factory.begin()` 은 요청이 끝날 때 커밋). 워커가 그 사이에 task 를 집어 실행하면
`find_by_id` 가 아직 커밋 안 된 row 를 못 찾아 `None` 을 반환하고, task 는 조용히
no-op 후 종료된다 (`worker/tasks/generate_summary.py`) — summary 는 PENDING 에서
영구히 멈추고 에러/알림/재시도 없이 사라진다. 실제로 monthly 생성 요청에서 재현됨
(task 가 10초가 아니라 0.003초만에 "성공" — find_by_id is None 조기 리턴과 일치).

수정: enqueue 는 라우터가 BackgroundTasks 로 예약해 커밋 시점에 더 가깝게 미룬다
(`summary_router.py:generate_summary`) — 레이스 윈도우를 줄이긴 하지만, 이 스택
(dishka ContainerMiddleware + Starlette)에서 BackgroundTasks 도 요청 스코프 세션
커밋보다 먼저 실행되므로 완전히 없애지는 못한다. 실제 정합성 보장은 워커 쪽
`SummaryRowNotYetVisibleError` 재시도가 담당한다 (`test_generate_summary_retries_...`
참고). 이 테스트는 use case 가 다시 task 를 직접 건드리는 회귀만 막는다.
"""
from datetime import date

import app.worker.tasks.generate_summary as generate_summary_module
from app.retrospective.application.dtos.summary_commands import RequestSummaryCommand
from app.retrospective.application.use_cases.request_summary import RequestSummaryUseCase
from app.retrospective.domain.models.value_objects import SummaryStatus, SummaryType


class _FakeSummaryRepo:
    async def find_by_period(
        self, user_id: str, summary_type: SummaryType, period_start: date
    ):
        return None

    async def save(self, summary):
        return summary


class _FakeRateLimiter:
    async def check_and_record(self, user_id: str, summary_type: SummaryType) -> None:
        return None


async def test_execute_never_touches_generate_summary_task(monkeypatch) -> None:
    calls: list[tuple[tuple, dict]] = []
    monkeypatch.setattr(
        generate_summary_module.generate_summary_task,
        "apply_async",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    use_case = RequestSummaryUseCase(_FakeSummaryRepo(), _FakeRateLimiter())
    result = await use_case.execute(
        RequestSummaryCommand(
            user_id="usr_1",
            summary_type=SummaryType.MONTHLY,
            period_start=date(2026, 8, 1),
            force=False,
        )
    )

    assert result.status == SummaryStatus.PENDING
    assert calls == [], "use case 가 커밋 전에 task 를 직접 enqueue 하면 레이스 컨디션이 재발한다"
