from dataclasses import dataclass

from app.retrospective.domain.models.value_objects import RetroType
from app.shared.domain.models.base import BaseEntity


@dataclass(kw_only=True)
class RetroTemplate(BaseEntity):
    user_id: str
    retro_type: RetroType
    name: str
    content: str
    is_default: bool = False
