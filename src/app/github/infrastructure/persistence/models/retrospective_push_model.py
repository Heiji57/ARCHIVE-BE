from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database.base import Base


class RetrospectivePushModel(Base):
    __tablename__ = "retrospective_pushes"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "period_type", "period_key",
            name="uq_retro_pushes_user_period",
        ),
        Index("ix_retro_pushes_user_pushed_at", "user_id", "pushed_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    period_key: Mapped[str] = mapped_column(String(32), nullable=False)
    repository_id: Mapped[str] = mapped_column(String, nullable=False)
    repository_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    html_url: Mapped[str] = mapped_column(Text, nullable=False)
    pushed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
