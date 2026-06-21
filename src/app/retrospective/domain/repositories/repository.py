from abc import ABC, abstractmethod
from datetime import date

from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.retro_template import RetroTemplate
from app.retrospective.domain.models.summary_template import UserSummaryTemplate
from app.retrospective.domain.models.value_objects import RetroType, SummaryType


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

    @abstractmethod
    async def find_completed_in_range(
        self, user_id: str, summary_type: SummaryType, from_date: date, to_date: date
    ) -> list[RetroSummary]: ...


class IUserSummaryTemplateRepository(ABC):
    @abstractmethod
    async def save(self, template: UserSummaryTemplate) -> UserSummaryTemplate: ...

    @abstractmethod
    async def find_by_id(
        self, id: str, user_id: str
    ) -> UserSummaryTemplate | None: ...

    @abstractmethod
    async def find_by_user_and_type(
        self, user_id: str, summary_type: SummaryType
    ) -> list[UserSummaryTemplate]: ...

    @abstractmethod
    async def find_by_name(
        self, user_id: str, summary_type: SummaryType, name: str
    ) -> UserSummaryTemplate | None: ...

    @abstractmethod
    async def count_by_user_and_type(
        self, user_id: str, summary_type: SummaryType
    ) -> int: ...

    @abstractmethod
    async def delete(self, id: str, user_id: str) -> None: ...


class IRetroTemplateRepository(ABC):
    @abstractmethod
    async def save(self, template: RetroTemplate) -> RetroTemplate: ...

    @abstractmethod
    async def find_by_id(self, id: str, user_id: str) -> RetroTemplate | None: ...

    @abstractmethod
    async def find_by_user(self, user_id: str) -> list[RetroTemplate]: ...

    @abstractmethod
    async def find_by_user_and_type(
        self, user_id: str, retro_type: RetroType
    ) -> list[RetroTemplate]: ...

    @abstractmethod
    async def find_default_for_type(
        self, user_id: str, retro_type: RetroType
    ) -> RetroTemplate | None: ...

    @abstractmethod
    async def find_by_name(
        self, user_id: str, retro_type: RetroType, name: str
    ) -> RetroTemplate | None: ...

    @abstractmethod
    async def delete(self, id: str, user_id: str) -> None: ...
