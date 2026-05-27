from dataclasses import dataclass

from app.shared.domain.models.base import BaseEntity


@dataclass(kw_only=True)
class JournalEntry(BaseEntity):
    user_id: str
    date_key: str  # YYYY-MM-DD — UK(user_id, date_key)
    title: str
    content: str
