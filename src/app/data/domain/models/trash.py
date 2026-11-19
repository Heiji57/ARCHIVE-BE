from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

TRASH_RETENTION = timedelta(days=30)

TrashKind = Literal["todo", "entry"]
TRASH_KINDS: tuple[TrashKind, ...] = ("todo", "entry")


@dataclass(frozen=True)
class TrashItem:
    kind: TrashKind
    id: str
    title: str
    date_key: str
    deleted_at: datetime

    @property
    def purge_at(self) -> datetime:
        return self.deleted_at + TRASH_RETENTION
