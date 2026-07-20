from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    status: str
    code: str
    data: T | None

    @classmethod
    def ok(cls, data: T) -> "ApiResponse[T]":
        return cls(status="success", code="OK", data=data)

    @classmethod
    def created(cls, data: T) -> "ApiResponse[T]":
        return cls(status="success", code="CREATED", data=data)

    @classmethod
    def accepted(cls, data: T) -> "ApiResponse[T]":
        return cls(status="accepted", code="ACCEPTED", data=data)


class PaginatedData(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


class PaginationQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)
