import calendar
from datetime import date, datetime, timedelta, timezone

from app.retrospective.application.dtos.summary_commands import RequestSummaryCommand
from app.retrospective.domain.exceptions.exceptions import SummaryAlreadyInProgressException
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import SummaryStatus, SummaryType
from app.retrospective.domain.repositories.repository import IRetroSummaryRepository
from app.shared.domain.utils.id import generate_id


class RequestSummaryUseCase:
    def __init__(self, summary_repo: IRetroSummaryRepository) -> None:
        self._summary_repo = summary_repo

    async def execute(self, cmd: RequestSummaryCommand) -> RetroSummary:
        period_start, period_end = _calculate_period(cmd.summary_type, cmd.period_start)

        existing = await self._summary_repo.find_by_period(
            cmd.user_id, cmd.summary_type, period_start
        )

        if existing:
            if existing.status in (SummaryStatus.PENDING, SummaryStatus.IN_PROGRESS):
                raise SummaryAlreadyInProgressException()
            if existing.status == SummaryStatus.COMPLETED:
                return existing
            # FAILED → 재시도: 상태 초기화 후 재실행
            now = datetime.now(timezone.utc)
            existing.status = SummaryStatus.PENDING
            existing.content = None
            existing.updated_at = now
            saved = await self._summary_repo.save(existing)
        else:
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

        # 순환 임포트 방지를 위해 지연 임포트
        from app.worker.tasks.generate_summary import generate_summary_task
        generate_summary_task.delay(saved.id, cmd.user_id)

        return saved


def _calculate_period(
    summary_type: SummaryType, period_start: date | None
) -> tuple[date, date]:
    if period_start is not None:
        if summary_type == SummaryType.WEEKLY:
            return period_start, period_start + timedelta(days=6)
        if summary_type == SummaryType.MONTHLY:
            last_day = calendar.monthrange(period_start.year, period_start.month)[1]
            return period_start, period_start.replace(day=last_day)
        # ANNUAL
        return period_start, period_start.replace(month=12, day=31)

    today = date.today()

    if summary_type == SummaryType.WEEKLY:
        # 직전 완전한 월~일 (오늘 기준 지난 주)
        last_sunday = today - timedelta(days=today.weekday() + 1)
        last_monday = last_sunday - timedelta(days=6)
        return last_monday, last_sunday

    if summary_type == SummaryType.MONTHLY:
        first_of_last = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        last_day = calendar.monthrange(first_of_last.year, first_of_last.month)[1]
        return first_of_last, first_of_last.replace(day=last_day)

    # ANNUAL
    last_year = today.year - 1
    return date(last_year, 1, 1), date(last_year, 12, 31)
