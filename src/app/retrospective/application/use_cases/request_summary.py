from datetime import datetime, timezone

from app.retrospective.application.dtos.summary_commands import RequestSummaryCommand
from app.retrospective.domain.exceptions.exceptions import SummaryAlreadyInProgressException
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import SummaryStatus
from app.retrospective.domain.repositories.repository import IRetroSummaryRepository
from app.retrospective.domain.utils.summary_period import calculate_summary_period
from app.retrospective.infrastructure.cache.summary_rate_limiter import SummaryRateLimiter
from app.shared.domain.utils.id import generate_id


class RequestSummaryUseCase:
    def __init__(
        self,
        summary_repo: IRetroSummaryRepository,
        rate_limiter: SummaryRateLimiter,
    ) -> None:
        self._summary_repo = summary_repo
        self._rate_limiter = rate_limiter

    async def execute(self, cmd: RequestSummaryCommand) -> RetroSummary:
        period_start, period_end = calculate_summary_period(cmd.summary_type, cmd.period_start)

        existing = await self._summary_repo.find_by_period(
            cmd.user_id, cmd.summary_type, period_start
        )

        if existing:
            if existing.status in (SummaryStatus.PENDING, SummaryStatus.IN_PROGRESS):
                raise SummaryAlreadyInProgressException()
            if existing.status == SummaryStatus.COMPLETED and not cmd.force:
                # 기존 완료본을 그대로 반환 (AI 재호출 안 함) — rate limit 카운트 대상 아님
                return existing
            # FAILED → 재시도, OR COMPLETED + force=True → 강제 재생성.
            # 둘 다 실제로 AI 호출이 발생하므로 rate limit 적용.
            await self._rate_limiter.check_and_record(cmd.user_id, cmd.summary_type)
            now = datetime.now(timezone.utc)
            existing.status = SummaryStatus.PENDING
            existing.content = None
            existing.updated_at = now
            saved = await self._summary_repo.save(existing)
        else:
            await self._rate_limiter.check_and_record(cmd.user_id, cmd.summary_type)
            now = datetime.now(timezone.utc)
            summary = RetroSummary(
                id=generate_id("summ"),
                user_id=cmd.user_id,
                summary_type=cmd.summary_type,
                period_start=period_start,
                period_end=period_end,
                status=SummaryStatus.PENDING,
                content=None,
                created_at=now,
            )
            saved = await self._summary_repo.save(summary)

        from app.worker.tasks.generate_summary import generate_summary_task
        generate_summary_task.apply_async(
            args=[saved.id, cmd.user_id],
            queue="ai_tasks",
            priority=9,
        )

        return saved
