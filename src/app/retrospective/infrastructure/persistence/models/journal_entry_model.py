from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database.base import Base


class JournalEntryModel(Base):
    __tablename__ = "journal_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date_key: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    retro_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="daily")
    folder_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("folders.id", ondelete="SET NULL"), nullable=True
    )
    content_tsv: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "date_key", "retro_type", name="uq_journal_entries_user_date_retro_type"),
        Index("ix_journal_entries_content_tsv", "content_tsv", postgresql_using="gin"),
        # (user_id, date_key) 범위 조회는 uq_journal_entries_user_date_retro_type 의
        # prefix 가 커버 — 별도 인덱스 불필요 (migration 027 에서 중복 제거).
        Index("ix_journal_entries_user_id_retro_type_date_key", "user_id", "retro_type", "date_key"),
        Index("ix_journal_entries_folder_id", "folder_id"),
    )
