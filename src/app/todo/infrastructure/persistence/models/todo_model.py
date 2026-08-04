from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
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
    # ── 반복 Todo 필드 ──────────────────────────────────────────────────────────
    recurrence_rule: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    series_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    original_date_key: Mapped[str | None] = mapped_column(String(10), nullable=True)
    original_start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    master_google_event_id: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(20)), nullable=False, server_default=text("'{}'")
    )
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
        # Google 원본 이벤트 → todo 승격 dedup 의 DB 레벨 최종 방어 + find_by_google_event_id
        # lookup 커버. 애플리케이션 dedup(find 후 insert)만으로는 동시 sync race 에서
        # 중복 승격 가능성이 남는다.
        Index(
            "uq_todos_user_google_event",
            "user_id",
            "google_event_id",
            unique=True,
            postgresql_where=text("google_event_id IS NOT NULL"),
        ),
        Index("ix_todos_tags_gin", "tags", postgresql_using="gin"),
        # 반복 시리즈 조회용 인덱스
        Index("ix_todos_series_id", "series_id", postgresql_where=text("series_id IS NOT NULL")),
        # exception row 의 중복 방어 — (series_id, original_date_key) 유니크
        Index(
            "uq_todos_series_original_date",
            "series_id",
            "original_date_key",
            unique=True,
            postgresql_where=text("series_id IS NOT NULL"),
        ),
    )
