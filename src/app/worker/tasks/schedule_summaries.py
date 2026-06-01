from datetime import date, datetime, timedelta, timezone

from celery import chain as celery_chain
from sqlalchemy import select

from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import SummaryStatus, SummaryType
from app.retrospective.infrastructure.persistence.repositories.retro_summary_repo import RetroSummaryRepository
from app.settings.infrastructure.persistence.models.user_settings_model import UserSettingsModel
from app.shared.domain.utils.id import generate_id
from app.shared.domain.utils.period import get_months_in_year, get_weeks_in_month
from app.worker.celery_app import celery_app
from app.worker.db import get_worker_session_factory

_SETTING_FILTER = {
    "weekly": UserSettingsModel.auto_summary_weekly.is_(True),
    "monthly": UserSettingsModel.auto_summary_monthly.is_(True),
    "annual": UserSettingsModel.auto_summary_yearly.is_(True),
}


async def _get_or_create_summary(
    summary_repo: RetroSummaryRepository,
    user_id: str,
    summary_type: SummaryType,
    period_start: date,
    period_end: date,
) -> RetroSummary | None:
    """Returns the summary to process, or None if already COMPLETED."""
    existing = await summary_repo.find_by_period(user_id, summary_type, period_start)

    if existing:
        if existing.status == SummaryStatus.COMPLETED:
            return None
        if existing.status in (SummaryStatus.PENDING, SummaryStatus.IN_PROGRESS):
            return existing
        # FAILED → reset for retry
        existing.status = SummaryStatus.PENDING
        existing.content = None
        existing.updated_at = datetime.now(timezone.utc)
        return await summary_repo.save(existing)

    summary = RetroSummary(
        id=generate_id("summ"),
        user_id=user_id,
        summary_type=summary_type,
        period_start=period_start,
        period_end=period_end,
        status=SummaryStatus.PENDING,
        content=None,
        created_at=datetime.now(timezone.utc),
    )
    return await summary_repo.save(summary)


async def _build_annual_chain(
    summary_repo: RetroSummaryRepository,
    user_id: str,
    year: int,
) -> list:
    from app.worker.tasks.generate_from_child_summaries import generate_from_child_summaries_task
    from app.worker.tasks.generate_summary import generate_summary_task

    tasks = []
    annual_start = date(year, 1, 1)
    annual_end = date(year, 12, 31)

    for m_start, m_end in get_months_in_year(year):
        for w_start, w_end in get_weeks_in_month(m_start.year, m_start.month):
            week_summary = await _get_or_create_summary(
                summary_repo, user_id, SummaryType.WEEKLY, w_start, w_end
            )
            if week_summary:
                tasks.append(
                    generate_summary_task.si(week_summary.id, user_id, send_notification=False)
                    .set(queue="ai_tasks", priority=2)
                )

        month_summary = await _get_or_create_summary(
            summary_repo, user_id, SummaryType.MONTHLY, m_start, m_end
        )
        if month_summary:
            tasks.append(
                generate_from_child_summaries_task.si(month_summary.id, user_id, send_notification=False)
                .set(queue="ai_tasks", priority=2)
            )

    annual_summary = await _get_or_create_summary(
        summary_repo, user_id, SummaryType.ANNUAL, annual_start, annual_end
    )
    if annual_summary:
        tasks.append(
            generate_from_child_summaries_task.si(annual_summary.id, user_id, send_notification=True)
            .set(queue="ai_tasks", priority=2)
        )

    return tasks


async def _build_monthly_chain(
    summary_repo: RetroSummaryRepository,
    user_id: str,
    m_start: date,
    m_end: date,
) -> list:
    from app.worker.tasks.generate_from_child_summaries import generate_from_child_summaries_task
    from app.worker.tasks.generate_summary import generate_summary_task

    tasks = []

    for w_start, w_end in get_weeks_in_month(m_start.year, m_start.month):
        week_summary = await _get_or_create_summary(
            summary_repo, user_id, SummaryType.WEEKLY, w_start, w_end
        )
        if week_summary:
            tasks.append(
                generate_summary_task.si(week_summary.id, user_id, send_notification=False)
                .set(queue="ai_tasks", priority=2)
            )

    month_summary = await _get_or_create_summary(
        summary_repo, user_id, SummaryType.MONTHLY, m_start, m_end
    )
    if month_summary:
        tasks.append(
            generate_from_child_summaries_task.si(month_summary.id, user_id, send_notification=True)
            .set(queue="ai_tasks", priority=2)
        )

    return tasks


@celery_app.task(name="worker.schedule_summaries")
async def schedule_summaries_task(schedule_type: str) -> None:
    """
    schedule_type: "weekly" | "monthly" | "annual"

    Beat 트리거 시점:
    - "weekly"  → 매주 월요일 01:00 UTC  (일요일이 끝난 직후)
    - "monthly" → 매월 1일   01:00 UTC  (전월 말일이 끝난 직후)
    - "annual"  → 매년 1월1일 01:00 UTC  (전년 12월31일이 끝난 직후)

    겹치는 날짜 처리 (annual > monthly > weekly 우선순위):
    - 1월 1일: annual이 주간·월간 전부 처리 → monthly, weekly는 early return
    - 매월 1일: monthly가 해당 월의 주간 포함 → weekly는 early return
    """
    today = date.today()

    if schedule_type == "monthly" and today.month == 1 and today.day == 1:
        return  # annual이 처리

    if schedule_type == "weekly" and today.day == 1:
        return  # monthly 또는 annual이 처리

    factory = get_worker_session_factory()

    async with factory.begin() as session:
        result = await session.execute(
            select(UserSettingsModel).where(_SETTING_FILTER[schedule_type])
        )
        users = result.scalars().all()

    for user_model in users:
        user_id = user_model.user_id
        chain_tasks: list = []

        async with factory.begin() as session:
            summary_repo = RetroSummaryRepository(session)

            if schedule_type == "annual":
                chain_tasks = await _build_annual_chain(summary_repo, user_id, today.year - 1)

            elif schedule_type == "monthly":
                last_month_last_day = today - timedelta(days=1)
                m_start = last_month_last_day.replace(day=1)
                m_end = last_month_last_day
                chain_tasks = await _build_monthly_chain(summary_repo, user_id, m_start, m_end)

            elif schedule_type == "weekly":
                from app.worker.tasks.generate_summary import generate_summary_task
                last_sunday = today - timedelta(days=1)
                last_monday = last_sunday - timedelta(days=6)
                week_summary = await _get_or_create_summary(
                    summary_repo, user_id, SummaryType.WEEKLY, last_monday, last_sunday
                )
                if week_summary:
                    chain_tasks = [
                        generate_summary_task.si(week_summary.id, user_id, send_notification=True)
                        .set(queue="ai_tasks", priority=2)
                    ]

        if chain_tasks:
            celery_chain(*chain_tasks).delay()
