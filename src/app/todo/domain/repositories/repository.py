from abc import ABC, abstractmethod

from app.todo.domain.models.todo import Todo


class ITodoRepository(ABC):
    @abstractmethod
    async def save(self, todo: Todo) -> Todo: ...

    @abstractmethod
    async def find_by_id(self, id: str, user_id: str) -> Todo | None: ...

    @abstractmethod
    async def find_by_date_key(self, user_id: str, date_key: str) -> list[Todo]: ...

    @abstractmethod
    async def find_by_full_text(
        self, user_id: str, query: str, page: int, size: int
    ) -> tuple[list[Todo], int]: ...

    @abstractmethod
    async def delete(self, id: str, user_id: str) -> None: ...
