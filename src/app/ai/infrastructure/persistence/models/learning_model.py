from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database.base import Base


class AiBehaviorEventModel(Base):
    """행동 학습 기록 — 추천에 대한 반응과 할 일 옮김·끝냄. 학습을 끄면 남기지 않는다."""

    __tablename__ = "ai_behavior_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    todo_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data: Mapped[dict] = mapped_column(  # type: ignore[type-arg]
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_ai_behavior_events_user_created", "user_id", "created_at"),)


class AiUserModelModel(Base):
    """이벤트에서 계산한 통계 캐시 — 새 이벤트가 들어오면 stale, 다음 추천 때 다시 계산."""

    __tablename__ = "ai_user_models"

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[dict] = mapped_column(JSONB, nullable=False)  # type: ignore[type-arg]
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
