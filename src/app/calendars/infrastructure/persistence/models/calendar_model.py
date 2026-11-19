from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database.base import Base


class CalendarModel(Base):
    __tablename__ = "calendars"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str] = mapped_column(String(8), nullable=False, server_default="c1")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    push_to_google: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_calendars_user_name"),
        # 사용자마다 기본 캘린더는 정확히 하나
        Index(
            "uq_calendars_user_default",
            "user_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )
