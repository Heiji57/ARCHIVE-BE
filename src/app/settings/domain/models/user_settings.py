from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.settings.domain.models.preferences import (
    DayEndReminder,
    EmailDigest,
    NotificationPrefs,
    QuietHours,
    WeekStart,
    WorkSchedule,
)


@dataclass(kw_only=True)
class UserSettings:
    user_id: str
    locale: str = "ko"
    auto_summary_weekly: bool = False
    auto_summary_monthly: bool = False
    auto_summary_yearly: bool = False
    notification_retention_days: int = 30
    # 신규 todo 생성 시 기본으로 Google Calendar 에 push 할지(생성 기본값 전용 —
    # 이미 연동된 todo 를 소급 변경하지 않는다). 사이드바에서 개별 override 가능.
    calendar_auto_push_todo: bool = False
    # Google Calendar 에서 cancelled 된 이벤트에 연동된 todo 처리 방침.
    # false(기본, 보수적): 연동 해제만(todo 유지). true(공격적): todo 도 함께 삭제.
    calendar_auto_delete_todo: bool = False
    last_summary_date_local: date | None = None
    github_push_target_repository_id: str | None = None
    # summary_type -> active template id. 키 부재 또는 null 이면 시스템 기본 템플릿 사용.
    # 활성 ID 가 가리키는 템플릿이 존재 / 동일 user 소유 / 동일 summary_type 인지는 set-active
    # use case 가 검증한다. delete-use-case 가 활성 보호로 임의 삭제를 차단한다.
    active_summary_template_ids: dict[str, str | None] = field(default_factory=dict)
    # retro_type -> active retro template id. 키 부재 또는 null 이면 기본 템플릿으로 폴백.
    active_retro_template_ids: dict[str, str | None] = field(default_factory=dict)
    # ── 리디자인 설정 (서버가 읽는 값) ─────────────────────────────────────
    week_start: WeekStart = "mon"
    work_schedule: WorkSchedule = field(default_factory=WorkSchedule)
    default_todo_minutes: int = 60
    day_end_reminder: DayEndReminder = field(default_factory=DayEndReminder)
    notification_prefs: NotificationPrefs = field(default_factory=NotificationPrefs)
    quiet_hours: QuietHours = field(default_factory=QuietHours)
    email_digest: EmailDigest = "off"
    # 화면에서만 쓰는 값 — 서버는 크기만 검증하고 해석하지 않는다(알 수 없는 키도 보존).
    ui_preferences: dict[str, Any] = field(default_factory=dict)
    # 예약 알림·주간 이메일 중복 발송 방지 (사용자 tz 날짜)
    last_due_reminder_date: date | None = None
    last_day_end_reminder_date: date | None = None
    last_weekly_email_date: date | None = None
    updated_at: datetime | None = None

    @classmethod
    def default(cls, user_id: str) -> "UserSettings":
        return cls(user_id=user_id)

    def active_template_id_for(self, summary_type: str) -> str | None:
        """summary_type 에 활성 지정된 템플릿 ID. 미설정/null 이면 None."""
        return self.active_summary_template_ids.get(summary_type)

    def active_retro_template_id_for(self, retro_type: str) -> str | None:
        """retro_type 에 활성 지정된 회고 템플릿 ID. 미설정/null 이면 None."""
        return self.active_retro_template_ids.get(retro_type)
