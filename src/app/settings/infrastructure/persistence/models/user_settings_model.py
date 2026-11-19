from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database.base import Base


class UserSettingsModel(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="ko")
    auto_summary_weekly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_summary_monthly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_summary_yearly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notification_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    calendar_auto_push_todo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    calendar_auto_delete_todo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    last_summary_date_local: Mapped[date | None] = mapped_column(Date, nullable=True)
    github_push_target_repository_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("github_repositories.id", ondelete="SET NULL"), nullable=True
    )
    active_summary_template_ids: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    active_retro_template_ids: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    week_start: Mapped[str] = mapped_column(String(3), nullable=False, server_default="mon")
    work_schedule: Mapped[dict] = mapped_column(  # type: ignore[type-arg]
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    default_todo_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("60")
    )
    day_end_reminder: Mapped[dict] = mapped_column(  # type: ignore[type-arg]
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    notification_prefs: Mapped[dict] = mapped_column(  # type: ignore[type-arg]
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    quiet_hours: Mapped[dict] = mapped_column(  # type: ignore[type-arg]
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    email_digest: Mapped[str] = mapped_column(String(10), nullable=False, server_default="off")
    ui_preferences: Mapped[dict] = mapped_column(  # type: ignore[type-arg]
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    last_due_reminder_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_day_end_reminder_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_weekly_email_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
