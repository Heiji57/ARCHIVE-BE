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
                )

        month_summary = await _get_or_create_summary(
            summary_repo, user_id, SummaryType.MONTHLY, m_start, m_end
        )
        if month_summary:
            tasks.append(
                generate_from_child_summaries_task.si(month_summary.id, user_id, send_notification=False)
            )

    annual_summary = await _get_or_create_summary(
        summary_repo, user_id, SummaryType.ANNUAL, annual_start, annual_end
    )
    if annual_summary:
        tasks.append(
            generate_from_child_summaries_task.si(annual_summary.id, user_id, send_notification=True)
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
            )

    month_summary = await _get_or_create_summary(
        summary_repo, user_id, SummaryType.MONTHLY, m_start, m_end
    )
    if month_summary:
        tasks.append(
            generate_from_child_summaries_task.si(month_summary.id, user_id, send_notification=True)
        )

    return tasks


@celery_app.task(name="worker.schedule_summaries")
async def schedule_summaries_task() -> None:
    """Daily task at 1am UTC: dispatches summary chains for auto-summary users."""
    factory = get_worker_session_factory()
    today = date.today()

    async with factory.begin() as session:
        result = await session.execute(
            select(UserSettingsModel).where(
                (UserSettingsModel.auto_summary_weekly.is_(True))
                | (UserSettingsModel.auto_summary_monthly.is_(True))
                | (UserSettingsModel.auto_summary_yearly.is_(True))
            )
        )
        users = result.scalars().all()

    for user_model in users:
        user_id = user_model.user_id
        chain_tasks: list = []

        async with factory.begin() as session:
            summary_repo = RetroSummaryRepository(session)

            if user_model.auto_summary_yearly and today.month == 1 and today.day == 1:
                chain_tasks = await _build_annual_chain(summary_repo, user_id, today.year - 1)

            elif user_model.auto_summary_monthly and today.day == 1:
                last_month_last_day = today - timedelta(days=1)
                m_start = last_month_last_day.replace(day=1)
                m_end = last_month_last_day
                chain_tasks = await _build_monthly_chain(summary_repo, user_id, m_start, m_end)

            elif user_model.auto_summary_weekly and today.weekday() == 0:
                last_sunday = today - timedelta(days=1)
                last_monday = last_sunday - timedelta(days=6)
                from app.worker.tasks.generate_summary import generate_summary_task
                week_summary = await _get_or_create_summary(
                    summary_repo, user_id, SummaryType.WEEKLY, last_monday, last_sunday
                )
                if week_summary:
                    chain_tasks = [
                        generate_summary_task.si(week_summary.id, user_id, send_notification=True)
                    ]

        if chain_tasks:
            celery_chain(*chain_tasks).delay()
