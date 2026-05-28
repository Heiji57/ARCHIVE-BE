from datetime import datetime

from pydantic import BaseModel

from app.retrospective.domain.models.journal_entry import JournalEntry


class EntryResponse(BaseModel):
    id: str
    user_id: str
    date_key: str
    title: str
    content: str
    retro_type: str
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def from_entity(cls, entry: JournalEntry) -> "EntryResponse":
        return cls(
            id=entry.id,
            user_id=entry.user_id,
            date_key=entry.date_key,
            title=entry.title,
            content=entry.content,
            retro_type=entry.retro_type.value,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )
