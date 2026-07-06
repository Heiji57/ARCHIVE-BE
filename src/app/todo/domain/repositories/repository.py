from abc import ABC, abstractmethod
from datetime import datetime

from app.todo.domain.models.todo import Todo


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
        """연결 해제 시 사용자의 모든 todo push 컬럼 초기화(연동 흔적 제거)."""
        ...

    @abstractmethod
    async def reset_failed_retry_counts(self, user_id: str) -> None:
        """재연결 시 failed 로 소진된 재시도 카운트 리셋 — 재연결만으로 재시도 재개."""
        ...
