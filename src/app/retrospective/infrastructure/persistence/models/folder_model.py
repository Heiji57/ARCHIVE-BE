from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database.base import Base


class FolderModel(Base):
    __tablename__ = "folders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    parent_folder_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("folders.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_folders_user_parent", "user_id", "parent_folder_id"),
        # (user_id, COALESCE(parent_folder_id,''), name) 유니크 인덱스는 migration 028 에서
        # raw SQL 로 생성 — SQLAlchemy 선언적 Index 는 COALESCE 표현식을 그대로 표현하기
        # 까다로워 여기서는 문서화만 하고 실제 제약은 DB 마이그레이션이 SST.
    )
