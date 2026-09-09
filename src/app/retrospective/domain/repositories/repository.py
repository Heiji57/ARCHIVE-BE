from abc import ABC, abstractmethod
from datetime import date

from app.retrospective.domain.models.folder import Folder
from app.retrospective.domain.models.journal_entry import JournalEntry, JournalEntryMeta
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
    async def find_meta_by_ids(self, user_id: str, ids: list[str]) -> list[JournalEntryMeta]:
        """find_by_id 의 batch 버전 — 토픽 매칭 결과(entry_id 목록)를 1회 IN 조회로 실체화.

        본문(`content`)과 전문검색 벡터(`content_tsv`)는 **싣지 않는다** — 호출자(주제
        매칭)가 읽지 않는데 행마다 가장 큰 컬럼이 딸려온다.
        """
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
    async def count_by_folder_ids(
        self, user_id: str, folder_ids: list[str]
    ) -> dict[str, int]:
        """폴더별 직속 엔트리 개수 (폴더 카드 entryCount 뱃지용)."""
        ...

    @abstractmethod
    async def find_by_folder_page(
        self,
        user_id: str,
        folder_id: str | None,
        retro_type: str | None,
        offset: int,
        limit: int,
    ) -> list[JournalEntry]:
        """폴더 뷰 통합 페이지네이션용 슬라이스 — date_key DESC, id DESC.
        id tie-break 는 필수다(같은 date_key 가 여러 건이면 정렬이 비결정적이라
        페이지 경계에서 누락/중복이 생긴다)."""
        ...

    @abstractmethod
    async def count_by_folder(
        self, user_id: str, folder_id: str | None, retro_type: str | None = None
    ) -> int:
        """폴더 뷰 통합 페이지네이션용 — 이 폴더 직계 엔트리 총건수."""
        ...

    @abstractmethod
    async def count_all_by_user_id(self, user_id: str) -> int:
        """사용자가 작성한 journal_entries 전체 개수 (all-time, AI 요약 제외)."""
        ...

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
    async def find_by_periods(
        self,
        user_id: str,
        summary_type: SummaryType,
        period_starts: list[date],
    ) -> list[RetroSummary]:
        """find_by_period 의 batch 버전 — annual dispatch 처럼 여러 period 를 순회하며
        개별 조회(N+1)하는 대신 1회 IN 조회로 처리하기 위해 사용."""
        ...

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
        summary_type: SummaryType | None,
        page: int,
        size: int,
        q: str | None,
        from_date: date | None,
        to_date: date | None,
    ) -> tuple[list[RetroSummary], int]:
        """전체 이력 페이지네이션(period_start desc). summary_type 미지정 시
        전체 타입(weekly/monthly/annual) 대상. q 는 content/edited_content ILIKE.
        from_date/to_date 있으면 기간 겹침(overlap) 필터 — period_end >= from_date AND
        period_start <= to_date (엄격 포함이 아니라, 조회 범위와 겹치는 요약을 모두 포함)."""
        ...

    @abstractmethod
    async def count_by_folder_ids(
        self, user_id: str, folder_ids: list[str]
    ) -> dict[str, int]:
        """폴더별 직속 요약 개수 (폴더 카드 entryCount 뱃지용)."""
        ...

    @abstractmethod
    async def find_by_folder_page(
        self,
        user_id: str,
        folder_id: str | None,
        summary_type: SummaryType | None,
        offset: int,
        limit: int,
    ) -> list[RetroSummary]:
        """폴더 뷰 통합 페이지네이션용 슬라이스 — period_start DESC, id DESC."""
        ...

    @abstractmethod
    async def count_by_folder(
        self, user_id: str, folder_id: str | None, summary_type: SummaryType | None = None
    ) -> int:
        """폴더 뷰 통합 페이지네이션용 — 이 폴더 직계 요약 총건수."""
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


class IFolderRepository(ABC):
    @abstractmethod
    async def save(self, folder: Folder) -> Folder: ...

    @abstractmethod
    async def find_by_id(self, id: str, user_id: str) -> Folder | None: ...

    @abstractmethod
    async def find_by_name(
        self, user_id: str, parent_folder_id: str | None, name: str
    ) -> Folder | None:
        """같은 부모(최상위 포함) 아래 이름 중복 검사용."""
        ...

    @abstractmethod
    async def find_children(
        self, user_id: str, parent_folder_id: str | None
    ) -> list[Folder]:
        """직계 하위 폴더 목록. parent_folder_id=None 이면 최상위 폴더들."""
        ...

    @abstractmethod
    async def find_all(self, user_id: str, limit: int) -> list[Folder]:
        """사용자의 전체 폴더(depth 무관) — name ASC, id ASC, 최대 limit 개.

        경로 조립(id → 이름 → 조상 사슬) 전용이다. 조상이 어느 깊이에 있을지
        알 수 없어 직계 조회로는 풀 수 없기 때문에 평평한 전체 집합을 준다."""
        ...

    @abstractmethod
    async def find_children_page(
        self, user_id: str, parent_folder_id: str | None, offset: int, limit: int
    ) -> list[Folder]:
        """직계 하위 폴더 슬라이스 — name ASC, id ASC (통합 페이지네이션의 앞 블록)."""
        ...

    @abstractmethod
    async def count_children(self, user_id: str, parent_folder_id: str | None) -> int:
        """직계 하위 폴더 총개수 (통합 페이지네이션의 folderTotal)."""
        ...

    @abstractmethod
    async def count_children_by_parent_ids(
        self, user_id: str, parent_ids: list[str]
    ) -> dict[str, int]:
        """폴더별 직계 하위 폴더 개수 (폴더 카드 folderCount 뱃지용)."""
        ...

    @abstractmethod
    async def find_ancestors(self, folder_id: str, user_id: str) -> list[Folder]:
        """자기 자신 제외 조상 체인(가까운 부모 → 최상위 순). 이동 시 순환참조 검증에 사용."""
        ...

    @abstractmethod
    async def delete(self, id: str, user_id: str) -> None: ...
