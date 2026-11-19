from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database.base import Base


class AiSuggestionModel(Base):
    __tablename__ = "ai_suggestions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    date_key: Mapped[str] = mapped_column(String(10), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    todo_id: Mapped[str] = mapped_column(String(128), nullable=False)  # 가상 회차 id 도 담는다
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)  # type: ignore[type-arg]
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    applied: Mapped[dict | None] = mapped_column(  # type: ignore[type-arg]
        JSONB(none_as_null=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "date_key", "kind", "todo_id", name="uq_ai_suggestions_key"),
        Index("ix_ai_suggestions_user_date", "user_id", "date_key"),
    )


class AiUsageModel(Base):
    __tablename__ = "ai_usage"

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    date_key: Mapped[str] = mapped_column(String(10), primary_key=True)
    requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
