from datetime import datetime

from pydantic import BaseModel

from app.retrospective.domain.models.retro_template import RetroTemplate


class RetroTemplateResponse(BaseModel):
    id: str
    user_id: str
    retro_type: str
    name: str
    content: str
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def from_entity(cls, template: RetroTemplate, *, is_active: bool = False) -> "RetroTemplateResponse":
        return cls(
            id=template.id,
            user_id=template.user_id,
            retro_type=template.retro_type.value,
            name=template.name,
            content=template.content,
            is_default=template.is_default,
            is_active=is_active,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )
