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
    last_schedule_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_summary_date_local: Mapped[date | None] = mapped_column(Date, nullable=True)
    github_push_target_repository_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("github_repositories.id", ondelete="SET NULL"), nullable=True
    )
    active_summary_template_ids: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
