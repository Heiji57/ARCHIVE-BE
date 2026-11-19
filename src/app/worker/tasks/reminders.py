"""예약 알림과 주간 이메일 — 사용자 tz 의 벽시계 시각에 맞춰 보낸다.

- `worker.dispatch_due_reminders` (5분): 일하는 날 첫 근무 시각에 "오늘 마감 n, 지난 마감 n"
  (둘 다 0 이면 안 보냄)
- `worker.dispatch_day_end_reminders` (5분): `day_end_reminder.at` 에 "남은 일 n" (링크 `day_close`)
- `worker.flush_quiet_notifications` (5분): 방해 금지가 끝난 보류 알림을 SSE 로 밀어 준다
- `worker.send_weekly_email` (매시간): `email_digest=weekly` 사용자에게 주 시작일 09시대에
  지난주 요약 메일

중복 방지: "시각이 지났고 아직 1시간이 안 됨" + "오늘 아직 안 보냄"(user_settings.last_*_date)을
함께 본다. 작업이 늦게 돌거나 두 번 돌아도 하루 한 번만 보낸다(엄격한 5분 창이면 한 번 늦은
beat 에 그날 알림이 사라진다). 사용자별 처리는 서로 격리한다(한 사용자 실패가 나머지를 막지 않게).
"""

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from redis.asyncio import Redis
from sqlalchemy import select

from app.notification.application.services.notifier import (
    STREAM_CHANNEL,
    Notifier,
    should_push_now,
    stream_payload,
)
from app.notification.domain.models.notification import Notification
from app.notification.domain.models.value_objects import NotificationCategory, NotificationType
from app.notification.infrastructure.persistence.repositories.notification_repo import (
    NotificationRepository,
)
from app.retrospective.domain.models.value_objects import SummaryStatus, SummaryType
from app.retrospective.infrastructure.persistence.repositories.journal_entry_repo import (
    JournalEntryRepository,
)
from app.retrospective.infrastructure.persistence.repositories.retro_summary_repo import (
    RetroSummaryRepository,
)
from app.settings.domain.models.preferences import js_weekday, parse_hhmm
from app.settings.domain.models.user_settings import UserSettings
from app.settings.infrastructure.persistence.repositories.user_settings_repo import (
    UserSettingsRepository,
)
from app.shared.domain.exceptions.external import EmailDeliveryFailedException
from app.shared.infrastructure.auth.jwt import create_unsubscribe_token
from app.shared.infrastructure.config.settings import get_settings
from app.shared.infrastructure.email.smtp import send_email
from app.todo.application.dtos.queries import GetTodosByDateQuery, GetTodosByRangeQuery
from app.todo.application.use_cases.get_todos_by_date import GetTodosByDateUseCase
from app.todo.application.use_cases.get_todos_by_range import GetTodosByRangeUseCase
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.infrastructure.persistence.repositories.todo_repo import TodoRepository
from app.user.infrastructure.persistence.models.user_model import UserModel
from app.user.infrastructure.persistence.repositories.user_repo import UserRepository
from app.worker.celery_app import celery_app
from app.worker.db import get_worker_session_factory

_log = structlog.get_logger(__name__)

# 정해진 시각부터 이 시간 안에 beat 가 돌면 보낸다(늦은 beat 보정). 그 뒤면 그날은 건너뛴다.
CATCH_UP = timedelta(hours=1)
WEEKLY_EMAIL_HOUR = 9
WEEKLY_EMAIL_CATCH_UP = timedelta(hours=3)  # SMTP 실패 시 다음 beat(매시간)에 다시 시도
_FLUSH_BATCH = 500
_CLOSED = (TaskStatus.DONE, TaskStatus.CANCELLED)

_TEXT: dict[str, dict[str, str]] = {
    "ko": {
        "due_title": "마감 알림",
        "due_msg": "오늘 마감 {today}개, 지난 마감 {overdue}개",
        "day_end_title": "오늘을 마무리할까요?",
        "day_end_msg": "남은 일 {left}개",
        "email_subject": "지난주 요약 ({start} ~ {end})",
        "email_body": (
            "지난주 요약 ({start} ~ {end})\n\n"
            "- 끝낸 일: {done}개\n- 회고: {retros}편\n- 마감 지난 일: {overdue}개\n"
            "{summary}\n앱에서 보기: {app_url}\n\n수신 거부: {unsubscribe_url}\n"
        ),
    },
    "en": {
        "due_title": "Due reminder",
        "due_msg": "{today} due today, {overdue} overdue",
        "day_end_title": "Ready to wrap up today?",
        "day_end_msg": "{left} left",
        "email_subject": "Your week ({start} – {end})",
        "email_body": (
            "Your week ({start} – {end})\n\n"
            "- Done: {done}\n- Retrospectives: {retros}\n- Overdue: {overdue}\n"
            "{summary}\nOpen the app: {app_url}\n\nUnsubscribe: {unsubscribe_url}\n"
        ),
    },
}


def _text(locale: str) -> dict[str, str]:
    base = (locale or "ko").split("-")[0].split("_")[0].lower()
    return _TEXT.get(base, _TEXT["en"])


# ── 시각 판정 (순수) ─────────────────────────────────────────────────────────


def _within(local_now: datetime, at: time, window: timedelta) -> bool:
    start = datetime.combine(local_now.date(), at, local_now.tzinfo)
    return start <= local_now < start + window


def due_reminder_ready(local_now: datetime, settings: UserSettings) -> bool:
    """일하는 날의 첫 근무 시각이 지났고(1시간 안), 오늘 아직 안 보냈다."""
    hours = settings.work_schedule.hours_on(local_now.date())
    if hours is None or settings.last_due_reminder_date == local_now.date():
        return False
    return _within(local_now, parse_hhmm(hours.start), CATCH_UP)


def day_end_reminder_ready(local_now: datetime, settings: UserSettings) -> bool:
    r = settings.day_end_reminder
    if not r.enabled or settings.last_day_end_reminder_date == local_now.date():
        return False
    return _within(local_now, parse_hhmm(r.at), CATCH_UP)


def week_start_index(settings: UserSettings) -> int:
    """주 시작 요일의 0(일)~6(토) 번호."""
    return 0 if settings.week_start == "sun" else 1


def weekly_email_ready(local_now: datetime, settings: UserSettings) -> bool:
    if settings.email_digest != "weekly" or settings.last_weekly_email_date == local_now.date():
        return False
    if js_weekday(local_now.date()) != week_start_index(settings):
        return False
    return _within(local_now, time(WEEKLY_EMAIL_HOUR, 0), WEEKLY_EMAIL_CATCH_UP)


# ── 공통 ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Target:
    user_id: str
    email: str
    tz: ZoneInfo


async def _targets(session) -> list[_Target]:  # type: ignore[no-untyped-def]
    rows = (await session.execute(select(UserModel.id, UserModel.email, UserModel.timezone))).all()
    out: list[_Target] = []
    for user_id, email, tz_str in rows:
        try:
            out.append(_Target(user_id, email, ZoneInfo(tz_str)))
        except (ZoneInfoNotFoundError, ValueError):
            _log.warning("reminders.invalid_timezone", user_id=user_id, timezone=tz_str)
    return out


async def _publish(redis: Redis, notification: Notification) -> None:
    await redis.publish(
        STREAM_CHANNEL.format(user_id=notification.user_id),
        json.dumps(stream_payload(notification)),
    )


def _notifier(session) -> Notifier:  # type: ignore[no-untyped-def]
    return Notifier(
        NotificationRepository(session), UserSettingsRepository(session), UserRepository(session)
    )


_SENT_FIELDS = ("last_due_reminder_date", "last_day_end_reminder_date", "last_weekly_email_date")


def _sent_marks(s: UserSettings) -> dict[str, date | None]:
    return {f: getattr(s, f) for f in _SENT_FIELDS}


async def _for_each_user(handler, now: datetime) -> None:  # type: ignore[no-untyped-def]
    """사용자마다 트랜잭션 하나. 한 사용자의 실패는 로그만 남기고 다음 사용자로 넘어간다."""
    factory = get_worker_session_factory()
    async with factory.begin() as session:
        targets = await _targets(session)
    redis = Redis.from_url(get_settings().redis.cache_url, decode_responses=True)
    try:
        for target in targets:
            structlog.contextvars.bind_contextvars(user_id=target.user_id)
            try:
                to_push: list[Notification] = []
                async with factory.begin() as session:
                    settings_repo = UserSettingsRepository(session)
                    settings = await settings_repo.find_by_user_id(target.user_id)
                    if settings is None:
                        # 설정 행이 없으면 기본값(월~금 09시 마감 알림 켜짐)으로 — 행을 만든다.
                        settings = await settings_repo.save(UserSettings.default(target.user_id))
                    local_now = now.astimezone(target.tz)
                    before = _sent_marks(settings)
                    pushed = await handler(session, target, settings, local_now)
                    if pushed is not None:
                        to_push.append(pushed)
                    changed = {
                        k: v
                        for k, v in _sent_marks(settings).items()
                        if before[k] != v and v is not None
                    }
                    if changed:
                        # 발송일만 갱신 — 그사이 사용자가 바꾼 다른 설정을 덮지 않는다.
                        await settings_repo.mark_sent(target.user_id, **changed)
                for n in to_push:
                    await _publish(redis, n)
            except Exception:
                # 사용자별 격리 경계 — 한 사용자의 실패가 다른 사용자의 알림을 막지 않게 한다.
                _log.exception("reminders.user_failed", user_id=target.user_id)
            finally:
                structlog.contextvars.unbind_contextvars("user_id")
    finally:
        await redis.aclose()


# ── 마감 알림 ───────────────────────────────────────────────────────────────


async def _due_reminder(session, target, settings, local_now):  # type: ignore[no-untyped-def]
    if not due_reminder_ready(local_now, settings):
        return None
    today = local_now.date()
    settings.last_due_reminder_date = today
    due_today, overdue = await TodoRepository(session).count_open_due(
        target.user_id, today.isoformat()
    )
    if due_today == 0 and overdue == 0:
        return None
    text = _text(settings.locale)
    saved = await _notifier(session).notify(
        target.user_id,
        type=NotificationType.WARNING if overdue else NotificationType.INFO,
        category=NotificationCategory.DUE,
        title=text["due_title"],
        message=text["due_msg"].format(today=due_today, overdue=overdue),
        link={"kind": "due"},
        settings=settings,
    )
    return saved if saved is not None and should_push_now(saved) else None


@celery_app.task(name="worker.dispatch_due_reminders")
async def dispatch_due_reminders_task() -> None:
    await _for_each_user(_due_reminder, datetime.now(UTC))


# ── 하루 마무리 알림 ─────────────────────────────────────────────────────────


async def _day_end_reminder(session, target, settings, local_now):  # type: ignore[no-untyped-def]
    if not day_end_reminder_ready(local_now, settings):
        return None
    today = local_now.date()
    settings.last_day_end_reminder_date = today
    todos = await GetTodosByDateUseCase(TodoRepository(session)).execute(
        GetTodosByDateQuery(user_id=target.user_id, date_key=today.isoformat())
    )
    left = sum(1 for t in todos if t.status not in _CLOSED)
    text = _text(settings.locale)
    saved = await _notifier(session).notify(
        target.user_id,
        type=NotificationType.INFO,
        category=NotificationCategory.SCHEDULE,
        title=text["day_end_title"],
        message=text["day_end_msg"].format(left=left),
        link={"kind": "day_close"},
        settings=settings,
    )
    return saved if saved is not None and should_push_now(saved) else None


@celery_app.task(name="worker.dispatch_day_end_reminders")
async def dispatch_day_end_reminders_task() -> None:
    await _for_each_user(_day_end_reminder, datetime.now(UTC))


# ── 방해 금지 보류 알림 내보내기 ─────────────────────────────────────────────


@celery_app.task(name="worker.flush_quiet_notifications")
async def flush_quiet_notifications_task() -> None:
    """보류 시각이 지난 알림을 SSE 로 보내고 보류를 푼다(보낸 뒤 해제 — 최소 한 번 전송)."""
    factory = get_worker_session_factory()
    redis = Redis.from_url(get_settings().redis.cache_url, decode_responses=True)
    try:
        while True:
            async with factory.begin() as session:
                repo = NotificationRepository(session)
                due = await repo.find_due_for_delivery(datetime.now(UTC), _FLUSH_BATCH)
                for n in due:
                    await _publish(redis, n)
                await repo.mark_delivered([n.id for n in due])
            if len(due) < _FLUSH_BATCH:
                break
    finally:
        await redis.aclose()


# ── 주간 이메일 ─────────────────────────────────────────────────────────────


def _first_paragraph(markdown: str) -> str:
    for block in markdown.split("\n\n"):
        text = block.strip()
        if text and not text.startswith("#"):
            return text
    return ""


async def _weekly_email(session, target, settings, local_now):  # type: ignore[no-untyped-def]
    if not weekly_email_ready(local_now, settings):
        return None
    today = local_now.date()
    start, end = today - timedelta(days=7), today - timedelta(days=1)

    todos = await GetTodosByRangeUseCase(TodoRepository(session)).execute(
        GetTodosByRangeQuery(
            user_id=target.user_id, from_date=start.isoformat(), to_date=end.isoformat()
        )
    )
    done = sum(1 for t in todos if t.status == TaskStatus.DONE)
    retros = len(await JournalEntryRepository(session).find_by_period(target.user_id, start, end))
    _, overdue = await TodoRepository(session).count_open_due(target.user_id, today.isoformat())
    summary = await RetroSummaryRepository(session).find_by_period(
        target.user_id, SummaryType.WEEKLY, start
    )
    summary_text = ""
    if summary is not None and summary.status == SummaryStatus.COMPLETED:
        body = summary.edited_content or (summary.content.text if summary.content else "")
        summary_text = _first_paragraph(body)

    cfg = get_settings()
    text = _text(settings.locale)
    unsubscribe_url = (
        f"{cfg.api_base_url}/api/v1/settings/email-digest/unsubscribe"
        f"?token={create_unsubscribe_token(target.user_id)}"
    )
    fmt: dict[str, Any] = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "done": done,
        "retros": retros,
        "overdue": overdue,
        "summary": f"\n{summary_text}\n" if summary_text else "",
        "app_url": cfg.frontend_url,
        "unsubscribe_url": unsubscribe_url,
    }
    try:
        await send_email(
            target.email,
            text["email_subject"].format(**fmt),
            text["email_body"].format(**fmt),
        )
    except EmailDeliveryFailedException:
        # 날짜를 찍지 않는다 — 다음 매시간 beat 가 (09~12시 안에서) 다시 시도한다.
        _log.warning("weekly_email.send_failed", user_id=target.user_id, exc_info=True)
        return None
    settings.last_weekly_email_date = today
    return None


@celery_app.task(name="worker.send_weekly_email")
async def send_weekly_email_task() -> None:
    await _for_each_user(_weekly_email, datetime.now(UTC))
