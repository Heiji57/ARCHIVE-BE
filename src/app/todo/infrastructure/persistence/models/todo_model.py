from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database.base import Base


class TodoModel(Base):
    __tablename__ = "todos"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    title_tsv: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    date_key: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ── Google Calendar push 상태 (쓰기는 타겟 SQL 전용, merge 관여 안 함) ────────
    calendar_push_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    google_event_id: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    push_intent: Mapped[str | None] = mapped_column(String(10), nullable=True)
    push_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_attempt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    push_retry_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )

    __table_args__ = (
        Index("ix_todos_title_tsv", "title_tsv", postgresql_using="gin"),
        Index("ix_todos_user_id_date_key", "user_id", "date_key"),
        Index(
            "ix_todos_calendar_push",
            "user_id",
            "updated_at",
            postgresql_where=text("calendar_push_status IS NOT NULL"),
        ),
    )
