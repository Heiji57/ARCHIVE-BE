from abc import ABC, abstractmethod
from datetime import date

from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import SummaryType


class IJournalEntryRepository(ABC):
    @abstractmethod
    async def save(self, entry: JournalEntry) -> JournalEntry: ...

    @abstractmethod
    async def find_by_id(self, id: str, user_id: str) -> JournalEntry | None: ...

    @abstractmethod
    async def find_by_date_key(
        self, user_id: str, date_key: str, retro_type: str
    ) -> JournalEntry | None: ...

    @abstractmethod
    async def find_by_period(
        self, user_id: str, start: date, end: date
    ) -> list[JournalEntry]: ...

    @abstractmethod
    async def find_by_retro_type(
        self, user_id: str, retro_type: str
    ) -> list[JournalEntry]: ...

    @abstractmethod
    async def find_by_full_text(
        self, user_id: str, query: str, page: int, size: int
    ) -> tuple[list[JournalEntry], int]: ...

    @abstractmethod
    async def delete(self, id: str, user_id: str) -> None: ...


class IRetroSummaryRepository(ABC):
    @abstractmethod
    async def save(self, summary: RetroSummary) -> RetroSummary: ...

    @abstractmethod
    async def find_by_id(self, id: str, user_id: str) -> RetroSummary | None: ...

    @abstractmethod
    async def find_by_period(
        self,
        user_id: str,
        summary_type: SummaryType,
        period_start: date,
    ) -> RetroSummary | None: ...

    @abstractmethod
    async def find_all_by_type(
        self, user_id: str, summary_type: SummaryType
    ) -> list[RetroSummary]: ...
