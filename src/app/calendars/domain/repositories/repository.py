from abc import ABC, abstractmethod

from app.calendars.domain.models.calendar import Calendar


class ICalendarRepository(ABC):
    @abstractmethod
    async def list_by_user(self, user_id: str) -> list[Calendar]:
        """sort_order, created_at 순."""
        ...

    @abstractmethod
    async def find_by_id(self, calendar_id: str, user_id: str) -> Calendar | None: ...

    @abstractmethod
    async def find_default(self, user_id: str) -> Calendar | None: ...

    @abstractmethod
    async def ensure_default(self, user_id: str, default: Calendar) -> Calendar:
        """기본 캘린더가 없으면 `default` 로 만들고, 있으면 있는 것을 돌려준다.

        동시에 처음 부른 두 요청이 둘 다 INSERT 해 유니크 위반(500)이 나지 않게 원자적으로.
        """
        ...

    @abstractmethod
    async def save(self, calendar: Calendar) -> Calendar: ...

    @abstractmethod
    async def delete(self, calendar_id: str, user_id: str) -> None:
        """그 캘린더의 할 일은 FK ON DELETE SET NULL 로 기본 캘린더(NULL)로 옮겨진다."""
        ...
