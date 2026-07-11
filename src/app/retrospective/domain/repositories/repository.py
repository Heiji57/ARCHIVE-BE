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
    async def id_exists(self, id: str) -> bool:
        """소유자 무관 전역 id 존재 여부. upsert(PUT /entries/:id) 의 생성 분기에서
        find_by_id(스코프 조회)가 None 이어도 그 id 가 '남의 엔트리'인지 '진짜 미존재'인지
        구분해 PK 탈취(merge 로 타 유저 행 덮어쓰기)를 막는 데 사용."""
        ...

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
        self, user_id: str, retro_type: str, since: date
    ) -> list[JournalEntry]:
        """retro_type 필터 조회 — date_key >= since 로 제한(무제한 전체 조회 방지).
        전체 이력이 필요하면 find_page 사용."""
        ...

    @abstractmethod
    async def find_page(
        self,
        user_id: str,
        retro_type: str | None,
        page: int,
        size: int,
        q: str | None,
        from_date: date | None,
        to_date: date | None,
    ) -> tuple[list[JournalEntry], int]:
        """전체 이력 페이지네이션(최신순) — 회고록 목록 페이지용. retro_type 미지정 시
        전체 타입 대상. q 있으면 content_tsv(제목+본문) 매칭. from_date/to_date 있으면
        date_key 범위로 필터."""
        ...

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

    @abstractmethod
    async def find_page(
        self,
        user_id: str,
        summary_type: SummaryType,
        page: int,
        size: int,
        q: str | None,
        from_date: date | None,
        to_date: date | None,
    ) -> tuple[list[RetroSummary], int]:
        """전체 이력 페이지네이션(period_start desc). q 는 content/edited_content ILIKE.
        from_date/to_date 있으면 기간 겹침(overlap) 필터 — period_end >= from_date AND
        period_start <= to_date (엄격 포함이 아니라, 조회 범위와 겹치는 요약을 모두 포함)."""
        ...


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
