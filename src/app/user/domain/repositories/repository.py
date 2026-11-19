from abc import ABC, abstractmethod
from datetime import datetime

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

    # ── 계정 삭제(soft delete) — 지운 계정은 모든 조회에서 빠진다(없는 계정처럼) ──
    @abstractmethod
    async def soft_delete(self, id: str) -> None: ...

    @abstractmethod
    async def find_deleted_before(self, before: datetime) -> list[User]:
        """완전 삭제 대상 — before 보다 먼저 지운 계정."""
        ...

    @abstractmethod
    async def purge(self, id: str) -> None:
        """users 행을 지운다(FK CASCADE 로 소유 데이터도). 지운 계정만."""
        ...
