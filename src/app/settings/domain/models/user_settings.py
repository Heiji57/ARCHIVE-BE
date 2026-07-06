from dataclasses import dataclass, field
from datetime import date, datetime


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
    last_schedule_check_at: datetime | None = None
    last_summary_date_local: date | None = None
    github_push_target_repository_id: str | None = None
    # summary_type -> active template id. 키 부재 또는 null 이면 시스템 기본 템플릿 사용.
    # 활성 ID 가 가리키는 템플릿이 존재 / 동일 user 소유 / 동일 summary_type 인지는 set-active
    # use case 가 검증한다. delete-use-case 가 활성 보호로 임의 삭제를 차단한다.
    active_summary_template_ids: dict[str, str | None] = field(default_factory=dict)
    # retro_type -> active retro template id. 키 부재 또는 null 이면 기본 템플릿으로 폴백.
    active_retro_template_ids: dict[str, str | None] = field(default_factory=dict)
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
