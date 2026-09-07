from pydantic import BaseModel, Field


class CreateTopicRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
