from dataclasses import dataclass

from app.retrospective.domain.models.value_objects import RetroType


@dataclass(frozen=True)
class CreateRetroTemplateCommand:
    user_id: str
    retro_type: RetroType
    name: str
    content: str


@dataclass(frozen=True)
class UpdateRetroTemplateCommand:
    user_id: str
    template_id: str
    name: str | None = None
    content: str | None = None


@dataclass(frozen=True)
class DeleteRetroTemplateCommand:
    user_id: str
    template_id: str


@dataclass(frozen=True)
class ResetRetroTemplateCommand:
    user_id: str
    template_id: str


@dataclass(frozen=True)
class SetActiveRetroTemplateCommand:
    user_id: str
    retro_type: RetroType
    template_id: str
