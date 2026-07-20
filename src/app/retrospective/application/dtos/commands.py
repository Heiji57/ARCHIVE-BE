from dataclasses import dataclass


@dataclass(frozen=True)
class CreateEntryCommand:
    user_id: str
    date_key: str
    title: str
    content: str
    retro_type: str


@dataclass(frozen=True)
class UpsertEntryCommand:
    entry_id: str
    user_id: str
    date_key: str
    title: str
    content: str
    retro_type: str
