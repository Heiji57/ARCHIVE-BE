from pydantic import BaseModel, field_validator

_VALID_RETRO_TYPES = {"daily", "weekly", "monthly", "yearly"}
_MAX_CONTENT_LENGTH = 4000


class CreateRetroTemplateRequest(BaseModel):
    name: str
    content: str

    @field_validator("content")
    @classmethod
    def content_length(cls, v: str) -> str:
        if len(v) > _MAX_CONTENT_LENGTH:
            raise ValueError(f"content must not exceed {_MAX_CONTENT_LENGTH} characters")
        return v


class UpdateRetroTemplateRequest(BaseModel):
    name: str | None = None
    content: str | None = None

    @field_validator("content")
    @classmethod
    def content_length(cls, v: str | None) -> str | None:
        if v is not None and len(v) > _MAX_CONTENT_LENGTH:
            raise ValueError(f"content must not exceed {_MAX_CONTENT_LENGTH} characters")
        return v


class SetActiveRetroTemplateRequest(BaseModel):
    retro_type: str
    template_id: str

    @field_validator("retro_type")
    @classmethod
    def retro_type_valid(cls, v: str) -> str:
        if v not in _VALID_RETRO_TYPES:
            raise ValueError(f"retro_type must be one of {_VALID_RETRO_TYPES}")
        return v
