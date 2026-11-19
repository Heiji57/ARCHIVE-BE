"""설정 확장(일하는 시간·방해 금지·알림 종류·화면 설정), 알림 생성 규칙, 예약 알림 시각,
주 시작 요일 반영.
"""
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.auth.domain.exceptions.exceptions import AuthTokenInvalidException
from app.notification.application.services.notifier import Notifier, stream_payload
from app.notification.domain.models.value_objects import NotificationCategory, NotificationType
from app.retrospective.domain.models.value_objects import SummaryType
from app.retrospective.domain.utils.summary_period import (
    adjust_week_after_start_change,
    calculate_summary_period,
)
from app.settings.application.dtos.commands import PatchSettingsCommand
from app.settings.application.use_cases.patch_settings import PatchSettingsUseCase
from app.settings.domain.exceptions.exceptions import SettingsUiPrefsTooLargeException
from app.settings.domain.models.preferences import (
    DayEndReminder,
    DayHours,
    NotificationPrefs,
    QuietHours,
    WorkSchedule,
)
from app.settings.domain.models.user_settings import UserSettings
from app.settings.presentation.requests.requests import (
    GeneralSettingsPatchRequest,
    NotificationSettingsPatchRequest,
    WorkSettingsPatchRequest,
)
from app.shared.domain.utils.period import week_of_month, week_start_of, weeks_owned_by_month
from app.shared.infrastructure.auth.jwt import (
    create_access_token,
    create_unsubscribe_token,
    decode_unsubscribe_token,
)
from app.worker.tasks.dispatch_summaries_for_tz import _resolve_schedule_type
from app.worker.tasks.reminders import (
    day_end_reminder_ready,
    due_reminder_ready,
    weekly_email_ready,
)

_SEOUL = ZoneInfo("Asia/Seoul")


def _local(y, m, d, hh, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=_SEOUL)


# ── 값 객체 ─────────────────────────────────────────────────────────────────


def test_work_schedule_hours_on_uses_first_day_fallback():
    ws = WorkSchedule(
        days=(1, 2, 5),
        per_day={1: DayHours("10:00", "19:00"), 5: DayHours("09:00", "15:00")},
    )
    assert ws.hours_on(date(2026, 11, 16)) == DayHours("10:00", "19:00")  # 월
    assert ws.hours_on(date(2026, 11, 17)) == DayHours("10:00", "19:00")  # 화 → 첫 일하는 날
    assert ws.hours_on(date(2026, 11, 20)) == DayHours("09:00", "15:00")  # 금
    assert ws.hours_on(date(2026, 11, 18)) is None  # 수 — 일하는 날 아님
    assert WorkSchedule.from_dict(ws.to_dict()) == ws


@pytest.mark.parametrize(
    ("hh", "mm", "inside"),
    [(23, 0, True), (2, 0, True), (7, 59, True), (8, 0, False), (22, 59, False)],
)
def test_quiet_hours_across_midnight(hh, mm, inside):
    q = QuietHours(enabled=True, start="23:00", end="08:00")
    assert q.contains(_local(2026, 11, 16, hh, mm)) is inside


def test_quiet_hours_end_is_next_morning():
    q = QuietHours(enabled=True, start="23:00", end="08:00")
    assert q.ends_after(_local(2026, 11, 16, 23, 30)) == _local(2026, 11, 17, 8)
    assert q.ends_after(_local(2026, 11, 17, 2, 0)) == _local(2026, 11, 17, 8)


def test_notification_prefs_system_cannot_be_turned_off():
    p = NotificationPrefs().merged({"due": False, "system": False})
    assert not p.allows("due") and p.allows("system") and p.allows("summary")


# ── 요청 검증 ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "body",
    [
        {"workSchedule": {"days": [1, 1]}},
        {"workSchedule": {"days": [7]}},
        {"workSchedule": {"days": [1], "perDay": {"1": {"from": "18:00", "to": "09:00"}}}},
        {"workSchedule": {"days": [1], "perDay": {"8": {"from": "09:00", "to": "18:00"}}}},
        {"dayEndReminder": {"enabled": True, "at": "24:00"}},
        {"defaultTodoMinutes": 10},
    ],
)
def test_work_section_rejects_invalid(body):
    with pytest.raises(ValidationError):
        WorkSettingsPatchRequest.model_validate(body)


def test_notification_section_parses_into_domain():
    req = NotificationSettingsPatchRequest.model_validate(
        {
            "quietHours": {"enabled": True, "from": "23:00", "to": "08:00"},
            "notificationPrefs": {"ai": False},
            "emailDigest": "weekly",
        }
    )
    got = req.provided()
    assert got["quiet_hours"] == QuietHours(True, "23:00", "08:00")
    assert got["notification_prefs"] == {"ai": False}
    assert got["email_digest"] == "weekly"


# ── 설정 저장 ───────────────────────────────────────────────────────────────


class _SettingsRepo:
    def __init__(self, s: UserSettings | None) -> None:
        self.s = s

    async def find_by_user_id(self, user_id):
        return self.s

    async def save(self, s):
        self.s = s
        return s


def _patch_uc(s: UserSettings | None = None):
    repo = _SettingsRepo(s or UserSettings(user_id="usr_1"))
    return PatchSettingsUseCase(repo, None), repo  # type: ignore[arg-type]


async def test_ui_preferences_merge_keeps_unknown_keys_and_null_deletes():
    uc, repo = _patch_uc(UserSettings(user_id="usr_1", ui_preferences={"startTab": "ai", "x": 1}))
    body = GeneralSettingsPatchRequest.model_validate(
        {"uiPreferences": {"timeFormat": "12h", "x": None, "futureKey": [1, 2]}}
    )
    await uc.execute(PatchSettingsCommand(user_id="usr_1", **body.provided()))
    assert repo.s.ui_preferences == {"startTab": "ai", "timeFormat": "12h", "futureKey": [1, 2]}


async def test_ui_preferences_over_8kb_rejected():
    uc, repo = _patch_uc()
    with pytest.raises(SettingsUiPrefsTooLargeException):
        await uc.execute(PatchSettingsCommand(user_id="usr_1", ui_preferences={"big": "x" * 9000}))
    assert repo.s.ui_preferences == {}


async def test_notification_prefs_patch_merges():
    uc, repo = _patch_uc()
    await uc.execute(PatchSettingsCommand(user_id="usr_1", notification_prefs={"due": False}))
    await uc.execute(PatchSettingsCommand(user_id="usr_1", notification_prefs={"ai": False}))
    assert repo.s.notification_prefs == NotificationPrefs(due=False, ai=False)


# ── 알림 생성 규칙 ──────────────────────────────────────────────────────────


class _NotifRepo:
    def __init__(self) -> None:
        self.saved = []

    async def save(self, n):
        self.saved.append(n)
        return n


class _Users:
    async def find_by_id(self, user_id):
        from types import SimpleNamespace

        return SimpleNamespace(timezone="Asia/Seoul")


def _notifier(settings: UserSettings):
    repo = _NotifRepo()
    return Notifier(repo, _SettingsRepo(settings), _Users()), repo  # type: ignore[arg-type]


async def _notify(notifier, category, now):
    return await notifier.notify(
        "usr_1",
        type=NotificationType.INFO,
        category=category,
        title="t",
        message="m",
        link={"kind": "todo", "id": "todo_1"},
        now=now,
    )


async def test_turned_off_category_is_not_created_but_system_is():
    settings = UserSettings(user_id="usr_1", notification_prefs=NotificationPrefs(due=False))
    notifier, repo = _notifier(settings)
    now = datetime(2026, 11, 16, 3, tzinfo=UTC)
    assert await _notify(notifier, NotificationCategory.DUE, now) is None
    assert await _notify(notifier, NotificationCategory.SYSTEM, now) is not None
    assert len(repo.saved) == 1


async def test_quiet_hours_defer_delivery_until_end():
    settings = UserSettings(
        user_id="usr_1", quiet_hours=QuietHours(enabled=True, start="23:00", end="08:00")
    )
    notifier, _ = _notifier(settings)
    # KST 11-17 00:30 → 08:00 KST = 11-16 23:00 UTC
    late_night = datetime(2026, 11, 16, 15, 30, tzinfo=UTC)
    n = await _notify(notifier, NotificationCategory.SUMMARY, late_night)
    assert n.deliver_after == datetime(2026, 11, 16, 23, 0, tzinfo=UTC)
    assert stream_payload(n)["link"] == {"kind": "todo", "id": "todo_1"}
    # 방해 금지 밖이면 바로 보낸다
    noon = datetime(2026, 11, 16, 3, tzinfo=UTC)
    n2 = await _notify(notifier, NotificationCategory.SUMMARY, noon)
    assert n2.deliver_after is None


# ── 예약 알림 시각 ──────────────────────────────────────────────────────────


def test_due_reminder_at_first_work_hour_once_per_day():
    s = UserSettings(user_id="usr_1")  # 월~금 09:00
    assert due_reminder_ready(_local(2026, 11, 16, 9, 2), s)
    assert due_reminder_ready(_local(2026, 11, 16, 9, 55), s)  # 늦은 beat 보정(1시간)
    assert not due_reminder_ready(_local(2026, 11, 16, 8, 59), s)
    assert not due_reminder_ready(_local(2026, 11, 16, 10, 5), s)
    assert not due_reminder_ready(_local(2026, 11, 15, 9, 2), s)  # 일요일 — 일하는 날 아님
    s.last_due_reminder_date = date(2026, 11, 16)
    assert not due_reminder_ready(_local(2026, 11, 16, 9, 30), s)  # 이미 보냄


def test_day_end_reminder_only_when_enabled():
    s = UserSettings(user_id="usr_1")
    assert not day_end_reminder_ready(_local(2026, 11, 16, 21, 31), s)
    s.day_end_reminder = DayEndReminder(enabled=True, at="21:30")
    assert day_end_reminder_ready(_local(2026, 11, 16, 21, 31), s)


def test_weekly_email_on_week_start_morning():
    s = UserSettings(user_id="usr_1", email_digest="weekly")
    assert weekly_email_ready(_local(2026, 11, 16, 9, 5), s)  # 월 09시
    assert not weekly_email_ready(_local(2026, 11, 15, 9, 5), s)  # 일 — 주 시작 아님
    s.week_start = "sun"
    assert weekly_email_ready(_local(2026, 11, 15, 10, 5), s)  # 일 10시(재시도 창)
    s.email_digest = "off"
    assert not weekly_email_ready(_local(2026, 11, 15, 9, 5), s)


def test_unsubscribe_token_round_trip_and_type_check():
    assert decode_unsubscribe_token(create_unsubscribe_token("usr_1")) == "usr_1"
    with pytest.raises(AuthTokenInvalidException):
        decode_unsubscribe_token(create_access_token("usr_1"))


# ── 주 시작 요일 ────────────────────────────────────────────────────────────


def test_week_start_of_and_weeks_by_month_sunday():
    assert week_start_of(date(2026, 11, 18), "mon") == date(2026, 11, 16)
    assert week_start_of(date(2026, 11, 18), "sun") == date(2026, 11, 15)
    weeks = weeks_owned_by_month(2026, 11, "sun")
    assert all(start.weekday() == 6 for start, _ in weeks)
    assert week_of_month(date(2026, 11, 18), "sun") == (2026, 11, 3)


def test_weekly_trigger_follows_week_start():
    assert _resolve_schedule_type(date(2026, 11, 16), "mon") == "weekly"
    assert _resolve_schedule_type(date(2026, 11, 15), "mon") is None
    assert _resolve_schedule_type(date(2026, 11, 15), "sun") == "weekly"


def test_manual_weekly_period_uses_week_start():
    assert calculate_summary_period(
        SummaryType.WEEKLY, None, "sun", today=date(2026, 11, 18)
    ) == (date(2026, 11, 8), date(2026, 11, 14))


_N8, _N9, _N14, _N15 = (date(2026, 11, d) for d in (8, 9, 14, 15))


@pytest.mark.parametrize(
    ("start", "end", "prev_end", "expected"),
    [
        # 월→일: 직전(월~일) 과 하루 겹침 → 6일
        (_N8, _N14, _N8, (_N9, _N14)),
        # 일→월: 첫 월요일의 주는 이미 덮임 → 건너뜀, 다음 주가 하루 더 가져가 8일
        (date(2026, 11, 2), date(2026, 11, 8), date(2026, 11, 7), None),
        (_N9, _N15, date(2026, 11, 7), (_N8, _N15)),
        # 평소 / 오래 쉰 뒤: 그대로
        (_N9, _N15, _N8, (_N9, _N15)),
        (_N9, _N15, date(2026, 10, 1), (_N9, _N15)),
    ],
)
def test_transition_week(start, end, prev_end, expected):
    assert adjust_week_after_start_change(start, end, prev_end) == expected


def test_push_key_keeps_monday_weeks_and_reads_sunday_weeks():
    from app.github.domain.utils.period_mapping import _weekly_key

    assert _weekly_key(date(2026, 11, 16)) == "2026-11-W3"  # 월요일 시작 주 — 기존과 같음
    assert _weekly_key(date(2026, 11, 15)) == "2026-11-W3"  # 일요일 시작 주




# ── 리뷰 반영 ───────────────────────────────────────────────────────────────


async def test_month_weeks_overlapping_old_alignment_are_skipped():
    from types import SimpleNamespace

    from app.worker.tasks.dispatch_summaries_for_tz import _covered_by_other_weeks

    class _Repo:
        async def find_overlapping(self, user_id, summary_type, start, end):
            # 주 시작을 바꾸기 전(월요일 정렬)에 만든 주간 요약
            return [SimpleNamespace(period_start=date(2026, 11, 2), period_end=date(2026, 11, 8))]

    weeks = [
        (date(2026, 11, 1), date(2026, 11, 7)),  # 새(일요일) 경계 — 옛 요약과 겹침
        (date(2026, 11, 8), date(2026, 11, 14)),  # 하루 겹침
        (date(2026, 11, 15), date(2026, 11, 21)),
    ]
    covered = await _covered_by_other_weeks(_Repo(), "usr_1", weeks)  # type: ignore[arg-type]
    assert covered == {weeks[0], weeks[1]}


def test_deferred_summary_notification_payload_keeps_summary_id():
    from app.notification.domain.models.notification import Notification

    n = Notification.create(
        user_id="usr_1",
        type=NotificationType.SUCCESS,
        category=NotificationCategory.SUMMARY,
        title="t",
        message="m",
        link={"kind": "summary", "id": "summ_1"},
    )
    payload = stream_payload(n)
    assert payload["resource"] == "summary" and payload["summaryId"] == "summ_1"


async def test_bad_user_timezone_falls_back_to_utc():
    from types import SimpleNamespace

    class _BadTz:
        async def find_by_id(self, user_id):
            return SimpleNamespace(timezone="Not/AZone")

    settings = UserSettings(
        user_id="usr_1", quiet_hours=QuietHours(enabled=True, start="23:00", end="08:00")
    )
    repo = _NotifRepo()
    notifier = Notifier(repo, _SettingsRepo(settings), _BadTz())  # type: ignore[arg-type]
    utc_late = datetime(2026, 11, 16, 23, 30, tzinfo=UTC)
    n = await _notify(notifier, NotificationCategory.SUMMARY, utc_late)
    assert n.deliver_after == datetime(2026, 11, 17, 8, 0, tzinfo=UTC)
