from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database.base import Base


class UserSummaryTemplateModel(Base):
    __tablename__ = "user_summary_templates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    summary_type: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "ix_user_summary_templates_user_type",
            "user_id", "summary_type",
        ),
        Index(
            "uq_user_summary_templates_user_type_name",
            "user_id", "summary_type", "name",
            unique=True,
        ),
    )
