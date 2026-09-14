from datetime import datetime, timezone

from app.retrospective.application.dtos.summary_commands import RequestSummaryCommand
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
            if existing.status == SummaryStatus.COMPLETED and not cmd.force:
                # 기존 완료본을 그대로 반환 (AI 재호출 안 함) — rate limit 카운트 대상 아님
                return existing
            # PENDING/IN_PROGRESS → 덮어쓰기, FAILED → 재시도, COMPLETED+force → 강제 재생성.
            # 실제로 AI 호출이 발생하므로 rate limit 적용.
            await self._rate_limiter.check_and_record(cmd.user_id, cmd.summary_type)
            now = datetime.now(timezone.utc)
            existing.status = SummaryStatus.PENDING
            existing.content = None
            existing.edited_content = None  # 재생성 시 편집 오버라이드 초기화 (AI 원본으로 복구)
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

        # AI task enqueue 는 여기서 하지 않는다 — 라우터가 BackgroundTasks 로 예약해
        # 커밋 시점에 더 가깝게 미룬다 (레이스 윈도우 축소). 워커가 커밋 전 row 를
        # 못 찾는 경우의 실제 정합성 보장은 worker/tasks/generate_summary.py 의
        # SummaryRowNotYetVisibleError 재시도가 담당한다.
        return saved
