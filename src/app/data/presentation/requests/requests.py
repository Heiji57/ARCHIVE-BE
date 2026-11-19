from typing import Literal

from pydantic import BaseModel, Field


class RequestExportRequest(BaseModel):
    scopes: list[Literal["retro", "todo", "ai"]] = Field(min_length=1, max_length=3)
    format: Literal["md", "json"] = "md"
