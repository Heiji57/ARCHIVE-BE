from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
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
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
