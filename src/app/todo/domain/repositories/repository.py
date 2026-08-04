from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.todo.domain.models.todo import Todo


@dataclass(frozen=True)
class WeeklyTrendDay:
    date_key: str
    done_count: int


@dataclass(frozen=True)
class TagCount:
    tag: str
    count: int


@dataclass(frozen=True)
class TodoStatsRaw:
    total: int
    done_count: int
    in_progress_count: int
    not_start_count: int
    weekly_trend: list[WeeklyTrendDay]
    tag_distribution: list[TagCount]


class ITodoRepository(ABC):
    @abstractmethod
    async def save(self, todo: Todo) -> Todo: ...

    @abstractmethod
    async def find_by_id(self, id: str, user_id: str) -> Todo | None: ...

    @abstractmethod
    async def find_by_date_key(self, user_id: str, date_key: str) -> list[Todo]: ...

    @abstractmethod
    async def find_by_date_range(
        self, user_id: str, from_date: str, to_date: str
    ) -> list[Todo]: ...

    @abstractmethod
    async def find_by_full_text(
        self, user_id: str, query: str, page: int, size: int
    ) -> tuple[list[Todo], int]: ...

    @abstractmethod
    async def delete(self, id: str, user_id: str) -> None: ...

    @abstractmethod
    async def find_by_google_event_id(
        self, user_id: str, google_event_id: str
    ) -> Todo | None:
        """google_event_id 로 연동된 todo 조회 — Google 원본 이벤트 승격 시 dedup,
        cancelled 이벤트 처리 시 연동 todo 식별에 사용."""
        ...

    @abstractmethod
    async def find_by_google_event_ids(
        self, user_id: str, google_event_ids: list[str]
    ) -> list[Todo]:
        """find_by_google_event_id 의 batch 버전 — 캘린더 동기화 시 이벤트별 개별
        조회(N+1) 대신 1회 IN 조회로 처리하기 위해 사용."""
        ...

    @abstractmethod
    async def create_from_calendar_event(self, todo: Todo) -> Todo | None:
        """Google Calendar 원본 이벤트를 Todo 로 최초 승격 — content + push 제어
        컬럼(calendar_push_status/google_event_id 등)을 한 번에 INSERT 한다.
        save()/merge() 는 push 컬럼을 의도적으로 건드리지 않으므로 이 전용 경로가 필요.
        동일 (user_id, google_event_id) 가 이미 존재하면(동시 sync race) None — DB 의
        partial unique(uq_todos_user_google_event) + ON CONFLICT DO NOTHING 으로 방어."""
        ...

    @abstractmethod
    async def clear_calendar_link(self, todo_id: str, user_id: str) -> None:
        """Google 쪽에서 이벤트가 사라졌을 때(cancelled) 단건 연동 흔적만 제거.
        bulk_clear_calendar_push(사용자 전체, 연결 해제 시)와 달리 todo 자체는 유지하고
        이 todo 하나만 unlink — 재push 시도 없음."""
        ...

    # ── Google Calendar push 상태 관리 (타겟 SQL 전용) ──────────────────────────
    # 아래 메서드들은 push 제어 컬럼(calendar_push_status/push_intent/push_started_at/
    # sync_attempt_id/push_retry_count/google_event_id)을 콘텐츠 save(merge)와 분리해
    # 관리한다. 워커 push 진행 상태와 사용자 편집 사이의 lost-update/clobber 방지.

    @abstractmethod
    async def mark_for_push(self, todo_id: str, user_id: str) -> None:
        """사용자 행동으로 콘텐츠 push 예약 — status='pending', intent='push',
        retry_count=0, sync_attempt_id/push_started_at=NULL. google_event_id 는 보존
        (기존 이벤트가 있으면 update, 없으면 create)."""
        ...

    @abstractmethod
    async def mark_for_delete(self, todo_id: str, user_id: str) -> None:
        """연동 해제 예약 — status='pending_delete', intent='delete', retry_count=0,
        sync_attempt_id/push_started_at=NULL. google_event_id 보존(삭제 대상 식별용)."""
        ...

    @abstractmethod
    async def claim_pending_pushes(
        self,
        user_id: str,
        attempt_id: str,
        max_retries: int,
        stuck_before: datetime,
        batch_size: int,
    ) -> list[Todo]:
        """배치 claim — 처리 대상 todo 를 원자적으로 'syncing' 마킹하고 반환.

        SKIP LOCKED 로 동시 워커의 중복 claim 방지. staleness 게이트는 'syncing'
        상태에만 적용(stuck 워커 재claim). 반환된 각 Todo 는 push_intent /
        google_event_id(=claim 시점 스냅샷) / sync_attempt_id(=attempt_id) 를 싣는다."""
        ...

    @abstractmethod
    async def claim_single_pending_push(
        self, todo_id: str, user_id: str, attempt_id: str
    ) -> Todo | None:
        """즉시 단건 claim — pending / pending_delete 상태의 특정 todo 를 'syncing'
        마킹하고 반환. 이미 배치가 가져갔거나(다른 상태) 없으면 None."""
        ...

    @abstractmethod
    async def heartbeat_push(self, todo_id: str, user_id: str, attempt_id: str) -> bool:
        """처리 직전 push_started_at 갱신(소유권 유지 확인). attempt_id 불일치(재claim
        당함)면 False → 호출자는 이 항목 처리를 건너뛴다."""
        ...

    @abstractmethod
    async def finalize_push_success(
        self, todo_id: str, user_id: str, attempt_id: str, google_event_id: str
    ) -> bool:
        """콘텐츠 push 성공 반영 — status='synced', google_event_id 세팅, 나머지 정리.
        attempt_id 가드. affected=0(재claim/사용자 편집으로 상태 변경)이면 False."""
        ...

    @abstractmethod
    async def finalize_delete_success(
        self, todo_id: str, user_id: str, attempt_id: str
    ) -> bool:
        """연동 해제 성공 반영 — 모든 push 컬럼 NULL/0(완전 unlink). attempt_id 가드."""
        ...

    @abstractmethod
    async def finalize_push_failure(
        self, todo_id: str, user_id: str, attempt_id: str, retry_count: int
    ) -> bool:
        """push/delete 실패 반영 — status='failed', retry_count 증가. push_intent /
        google_event_id 는 보존(재시도 시 의도/대상 유지). attempt_id 가드."""
        ...

    @abstractmethod
    async def bulk_clear_calendar_push(self, user_id: str) -> None:
        """연결 해제 시 사용자의 모든 todo push 활성 상태 초기화.

        google_event_id 는 보존한다 — 재연결 시 find_by_google_event_id 의 dedup 키로
        재사용돼, 같은 Google 이벤트가 다음 full resync 에서 중복 todo 로 재생성되는
        것을 막는다(특히 Google 원본에서 승격된 todo — archiveTodoId 태그가 없어
        google_event_id 가 유일한 dedup 수단). calendar_push_status=NULL 이라 worker
        가 claim 대상(pending/pending_delete/failed/syncing)에서 제외해 안전하다."""
        ...

    @abstractmethod
    async def reset_failed_retry_counts(self, user_id: str) -> None:
        """재연결 시 failed 로 소진된 재시도 카운트 리셋 — 재연결만으로 재시도 재개."""
        ...

    # ── 반복 Todo 전용 ──────────────────────────────────────────────────────────

    @abstractmethod
    async def find_series_base(self, series_id: str, user_id: str) -> Todo | None:
        """series_id 로 base event 조회 (recurrence_rule IS NOT NULL, series_id IS NULL)."""
        ...

    @abstractmethod
    async def find_masters_overlapping(
        self, user_id: str, from_date: str, to_date: str
    ) -> list[Todo]:
        """조회 범위와 겹치는 반복 시리즈 base event 목록.

        겹침 조건: base.date_key <= to_date AND (until IS NULL OR until >= from_date).
        """
        ...

    @abstractmethod
    async def find_exceptions_batch(
        self, user_id: str, series_ids: list[str], from_date: str, to_date: str
    ) -> list[Todo]:
        """복수 시리즈의 exception row 를 1회 IN 조회로 가져온다.

        original_date_key 가 [from_date, to_date] 에 속하는 행만 반환.
        """
        ...

    @abstractmethod
    async def find_all_exceptions(self, series_id: str, user_id: str) -> list[Todo]:
        """시리즈 전체 exception row 조회 (삭제·이동 시 사용)."""
        ...

    @abstractmethod
    async def upsert_exception(self, todo: Todo) -> Todo:
        """exception row INSERT or UPDATE.

        ON CONFLICT (series_id, original_date_key) WHERE series_id IS NOT NULL
        DO UPDATE SET ... — 동시 요청 레이스 방어.
        """
        ...

    @abstractmethod
    async def delete_exceptions_from(
        self, series_id: str, user_id: str, from_date: str
    ) -> None:
        """original_date_key >= from_date 인 exception row 삭제 ("이후 전체 삭제" 시)."""
        ...

    @abstractmethod
    async def delete_all_exceptions(self, series_id: str, user_id: str) -> None:
        """시리즈의 모든 exception row 삭제 ("전체 삭제" 시)."""
        ...

    @abstractmethod
    async def get_todo_stats(
        self,
        user_id: str,
        range_from: str,
        range_to: str,
        week_from: str,
        week_to: str,
        tz: str,
    ) -> TodoStatsRaw:
        """대시보드 통계 집계.

        range_from/to = 상태 카운트·tag 분포 집계 범위 (YYYY-MM-DD).
        week_from/to  = weekly_trend 슬롯 범위 (항상 이번 ISO 주).
        tz            = completed_at → 로컬 날짜 변환용 IANA timezone.
        """
        ...
