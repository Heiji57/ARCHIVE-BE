from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database.base import Base


class ExportModel(Base):
    __tablename__ = "exports"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(10)), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    file_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_exports_user_created", "user_id", "created_at"),
        # 사용자당 진행 중 하나 — 동시 요청이 사전 검사를 함께 통과해도 늦은 쪽은 409.
        Index(
            "uq_exports_user_pending",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )
