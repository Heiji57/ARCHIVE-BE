from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class GitHubSettingsInput(BaseModel):
    """github 네임스페이스 — 향후 확장 가능. push_target_repository_id 미지정 시 null 유지(변경 없음)."""
    push_target_repository_id: str | None = Field(
        default=None, alias="pushTargetRepositoryId"
    )

    model_config = {"populate_by_name": True}


class UpdateSettingsRequest(BaseModel):
    locale: str = Field(default="ko", max_length=10)
    auto_summary_weekly: bool = Field(default=False, alias="autoSummaryWeekly")
    auto_summary_monthly: bool = Field(default=False, alias="autoSummaryMonthly")
    auto_summary_yearly: bool = Field(default=False, alias="autoSummaryYearly")
    notification_retention_days: int = Field(default=30, ge=1, le=365, alias="notificationRetentionDays")
    last_schedule_check_at: datetime | None = Field(default=None, alias="lastScheduleCheckAt")
    github: GitHubSettingsInput = Field(default_factory=GitHubSettingsInput)

    model_config = {"populate_by_name": True}

    @field_validator("locale")
    @classmethod
    def _normalize_locale(cls, v: str) -> str:
        return (v or "ko").strip().lower() or "ko"


class ActiveSummaryTemplateIdsRequest(BaseModel):
    """`PUT /settings/auto-summary/active` body.

    각 필드:
    - 문자열 → 해당 summary_type 의 활성 템플릿 id (소유/타입 일치 검증)
    - null   → 해당 type 비활성화 → 시스템 기본 템플릿 사용
    - 미전송 → 변경 안 함
    """
    weekly: str | None = Field(default=None)
    monthly: str | None = Field(default=None)
    annual: str | None = Field(default=None)

    model_config = {"populate_by_name": True}
