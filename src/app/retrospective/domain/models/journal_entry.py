from dataclasses import dataclass

from app.retrospective.domain.models.value_objects import RetroType
from app.shared.domain.models.base import BaseEntity


@dataclass(kw_only=True)
class JournalEntry(BaseEntity):
    user_id: str
    date_key: str  # YYYY-MM-DD
    title: str
    content: str
    retro_type: RetroType
    folder_id: str | None = None
