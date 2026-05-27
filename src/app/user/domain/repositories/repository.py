from abc import ABC, abstractmethod

from app.user.domain.models.user import User


class IUserRepository(ABC):
    @abstractmethod
    async def save(self, user: User) -> User: ...

    @abstractmethod
    async def find_by_id(self, id: str) -> User | None: ...

    @abstractmethod
    async def find_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    async def delete(self, id: str) -> None: ...
