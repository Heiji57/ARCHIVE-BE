"""사용자 tz 기반 자동 요약 dispatcher.

매시간 정각에 발사된다. 각 사용자의 timezone 기준 현재 시각이 "1am 대"(01:00 ~ 01:59)인 사용자만
선별해 fan-out한다. DST 중복 방지를 위해 user_settings.last_summary_date_local로 같은 현지 날짜 중복
실행을 차단한다. 부하 분산을 위해 사용자별 결정적 지터를 적용 (0 ~ SUMMARY_JITTER_SECONDS).

겹치는 날짜 우선순위: annual > monthly > weekly
- 1월 1일(현지): annual 트리거 → monthly/weekly skip
- 매월 1일(현지): monthly 트리거 → weekly skip
- 매주 월요일(현지): weekly 트리거
"""
import hashlib
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from celery import chain as celery_chain
from sqlalchemy import or_, select

from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import SummaryStatus, SummaryType
from app.retrospective.infrastructure.persistence.repositories.retro_summary_repo import (
    RetroSummaryRepository,
)
from app.settings.infrastructure.persistence.models.user_settings_model import UserSettingsModel
from app.shared.domain.utils.id import generate_id
from app.shared.domain.utils.period import get_months_in_year, weeks_owned_by_month
from app.user.infrastructure.persistence.models.user_model import UserModel
from app.worker.celery_app import celery_app
from app.worker.db import get_worker_session_factory

# 사용자별 결정적 지터 폭 (초). 0이면 정시 발사. 기본 1800초 = 0~30분 분산.
SUMMARY_JITTER_SECONDS = int(os.getenv("SUMMARY_JITTER_SECONDS", "1800"))

# 트리거 현지 시간대 — 01:00 ~ 01:59 사이의 사용자만 dispatch
TRIGGER_HOUR = 1


def _user_jitter_seconds(user_id: str) -> int:
    """사용자별 결정적 지터 — 같은 사용자는 항상 같은 초 만큼 지연."""
    if SUMMARY_JITTER_SECONDS <= 0:
        return 0
    digest = hashlib.sha256(user_id.encode()).hexdigest()
    return int(digest, 16) % SUMMARY_JITTER_SECONDS


def _resolve_schedule_type(local_date: date) -> str | None:
    """
    Returns: "annual" | "monthly" | "weekly" | None
    - 1월 1일 → annual
    - 매월 1일 (1/1 제외) → monthly
    - 월요일 (1일 제외) → weekly
    - 그 외 → None
    """
    if local_date.month == 1 and local_date.day == 1:
        return "annual"
    if local_date.day == 1:
        return "monthly"
    if local_date.weekday() == 0:  # Monday
        return "weekly"
    return None


async def _get_or_create_summary(
    summary_repo: RetroSummaryRepository,
    user_id: str,
    summary_type: SummaryType,
    period_start: date,
    period_end: date,
) -> RetroSummary | None:
    existing = await summary_repo.find_by_period(user_id, summary_type, period_start)
    now = datetime.now(timezone.utc)
    summary, needs_save = _reconcile_summary(
        existing, user_id, summary_type, period_start, period_end, now
    )
    if summary is None:
        return None
    return await summary_repo.save(summary) if needs_save else summary


def _reconcile_summary(
    existing: RetroSummary | None,
    user_id: str,
    summary_type: SummaryType,
    period_start: date,
    period_end: date,
    now: datetime,
) -> tuple[RetroSummary | None, bool]:
    """_get_or_create_summary 의 순수 버전 — 이미 batch 조회된 existing 을 받아 DB 를
    다시 조회하지 않는다. annual 처럼 다수 period 를 순회할 때 N+1 조회를 피하기 위해
    분리(읽기만 batch 화, 저장 로직/조건은 기존과 동일하게 유지).

    Returns: (enqueue 대상 summary 또는 None, save 필요 여부).
    COMPLETED 는 (None, False) — 재생성 불필요. PENDING/IN_PROGRESS 는 (existing, False)
    — 이미 대기 중이므로 저장 없이 그대로 enqueue.
    """
    if existing:
        if existing.status == SummaryStatus.COMPLETED:
            return None, False
        if existing.status in (SummaryStatus.PENDING, SummaryStatus.IN_PROGRESS):
            return existing, False
        existing.status = SummaryStatus.PENDING
        existing.content = None
        existing.edited_content = None  # 재생성 시 편집 오버라이드 초기화 (AI 원본으로 복구)
        existing.updated_at = now
        return existing, True

    summary = RetroSummary(
        id=generate_id("summ"),
        user_id=user_id,
        summary_type=summary_type,
        period_start=period_start,
        period_end=period_end,
        status=SummaryStatus.PENDING,
        content=None,
        created_at=now,
    )
    return summary, True


async def _build_chain_for_user(
    summary_repo: RetroSummaryRepository,
    user_id: str,
    schedule_type: str,
    local_today: date,
) -> list:
    """모든 summary 단계가 동일한 `generate_summary_task` 사용.

    데이터 소스 정책은 task 내부 strategy 에서 결정 (weekly=entries,
    monthly=hybrid, annual=hybrid). 따라서 dispatcher 는 fan-out 만 담당.
    """
    from app.worker.tasks.generate_summary import generate_summary_task

    def _enqueue(summary, *, notify: bool):
        tasks.append(
            generate_summary_task.si(
                summary.id, user_id, send_notification=notify
            ).set(queue="ai_tasks", priority=2)
        )

    tasks: list = []

    if schedule_type == "annual":
        year = local_today.year - 1
        now = datetime.now(timezone.utc)
        months = get_months_in_year(year)
        weeks_by_month = {
            m_start: weeks_owned_by_month(m_start.year, m_start.month) for m_start, _ in months
        }

        # 이 해의 모든 week/month period_start 를 모아 타입별 1회씩 batch 조회
        # (기존: period 마다 개별 find_by_period → 사용자당 최대 ~65회 조회).
        all_week_starts = [w_start for weeks in weeks_by_month.values() for w_start, _ in weeks]
        existing_weeks = {
            s.period_start: s
            for s in await summary_repo.find_by_periods(user_id, SummaryType.WEEKLY, all_week_starts)
        }
        existing_months = {
            s.period_start: s
            for s in await summary_repo.find_by_periods(
                user_id, SummaryType.MONTHLY, [m_start for m_start, _ in months]
            )
        }
        existing_annual = await summary_repo.find_by_period(
            user_id, SummaryType.ANNUAL, date(year, 1, 1)
        )

        for m_start, _ in months:
            for w_start, w_end in weeks_by_month[m_start]:
                week_summary, needs_save = _reconcile_summary(
                    existing_weeks.get(w_start), user_id, SummaryType.WEEKLY, w_start, w_end, now
                )
                if week_summary:
                    if needs_save:
                        week_summary = await summary_repo.save(week_summary)
                    _enqueue(week_summary, notify=False)
            month_summary, needs_save = _reconcile_summary(
                existing_months.get(m_start),
                user_id,
                SummaryType.MONTHLY,
                m_start,
                _month_end(m_start),
                now,
            )
            if month_summary:
                if needs_save:
                    month_summary = await summary_repo.save(month_summary)
                _enqueue(month_summary, notify=False)

        annual_summary, needs_save = _reconcile_summary(
            existing_annual, user_id, SummaryType.ANNUAL, date(year, 1, 1), date(year, 12, 31), now
        )
        if annual_summary:
            if needs_save:
                annual_summary = await summary_repo.save(annual_summary)
            _enqueue(annual_summary, notify=True)

    elif schedule_type == "monthly":
        last_month_last_day = local_today - timedelta(days=1)
        m_start = last_month_last_day.replace(day=1)
        m_end = last_month_last_day
        for w_start, w_end in weeks_owned_by_month(m_start.year, m_start.month):
            week_summary = await _get_or_create_summary(
                summary_repo, user_id, SummaryType.WEEKLY, w_start, w_end
            )
            if week_summary:
                _enqueue(week_summary, notify=False)
        month_summary = await _get_or_create_summary(
            summary_repo, user_id, SummaryType.MONTHLY, m_start, m_end
        )
        if month_summary:
            _enqueue(month_summary, notify=True)

    elif schedule_type == "weekly":
        last_sunday = local_today - timedelta(days=1)
        last_monday = last_sunday - timedelta(days=6)
        week_summary = await _get_or_create_summary(
            summary_repo, user_id, SummaryType.WEEKLY, last_monday, last_sunday
        )
        if week_summary:
            _enqueue(week_summary, notify=True)

    return tasks


def _month_end(month_start: date) -> date:
    import calendar
    return date(
        month_start.year,
        month_start.month,
        calendar.monthrange(month_start.year, month_start.month)[1],
    )


@celery_app.task(name="worker.dispatch_summaries_for_tz")
async def dispatch_summaries_for_tz_task() -> None:
    """매시간 정각 발사. 현지 1am 사용자 전원 fan-out."""
    factory = get_worker_session_factory()
    now_utc = datetime.now(timezone.utc)

    # 1. user_settings에서 자동 요약 활성 사용자 + user.timezone JOIN 조회
    async with factory.begin() as session:
        stmt = (
            select(
                UserModel.id,
                UserModel.timezone,
                UserSettingsModel.last_summary_date_local,
                UserSettingsModel.auto_summary_weekly,
                UserSettingsModel.auto_summary_monthly,
                UserSettingsModel.auto_summary_yearly,
            )
            .join(UserSettingsModel, UserSettingsModel.user_id == UserModel.id)
            .where(
                or_(
                    UserSettingsModel.auto_summary_weekly.is_(True),
                    UserSettingsModel.auto_summary_monthly.is_(True),
                    UserSettingsModel.auto_summary_yearly.is_(True),
                )
            )
        )
        result = await session.execute(stmt)
        rows = result.all()

    for row in rows:
        user_id, tz_str, last_local_date, weekly_on, monthly_on, yearly_on = row
        try:
            tz = ZoneInfo(tz_str)
        except Exception:
            continue  # 잘못된 tz는 skip

        local_now = now_utc.astimezone(tz)
        if local_now.hour != TRIGGER_HOUR:
            continue
        local_today = local_now.date()

        # DST 중복 방지 — 같은 현지 날짜에 이미 실행했으면 skip
        if last_local_date == local_today:
            continue

        schedule_type = _resolve_schedule_type(local_today)
        if schedule_type is None:
            continue

        # 사용자별 auto_summary_* 설정과 schedule_type 매칭
        type_to_flag = {
            "annual": yearly_on,
            "monthly": monthly_on,
            "weekly": weekly_on,
        }
        if not type_to_flag[schedule_type]:
            continue

        countdown = _user_jitter_seconds(user_id)

        async with factory.begin() as session:
            summary_repo = RetroSummaryRepository(session)
            chain_tasks = await _build_chain_for_user(
                summary_repo, user_id, schedule_type, local_today
            )
            # last_summary_date_local 갱신 (DST 중복 방지)
            settings_model = await session.get(UserSettingsModel, user_id)
            if settings_model is not None:
                settings_model.last_summary_date_local = local_today
                settings_model.updated_at = now_utc

        if chain_tasks:
            celery_chain(*chain_tasks).apply_async(countdown=countdown)
