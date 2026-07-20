from dataclasses import dataclass

from app.shared.domain.models.base import BaseEntity


@dataclass(kw_only=True)
class Folder(BaseEntity):
    user_id: str
    name: str
    parent_folder_id: str | None = None
