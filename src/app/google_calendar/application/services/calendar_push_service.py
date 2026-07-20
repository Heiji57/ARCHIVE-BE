from dataclasses import dataclass
from typing import Literal

from app.google_calendar.infrastructure.api.google_calendar_client import (
    CalendarEventWrite,
    GoogleCalendarApiClient,
)
from app.todo.domain.models.todo import RecurrenceRule, Todo
from app.todo.domain.utils.recurrence import build_gcal_instance_id

PushKind = Literal["push_success", "delete_success", "failure"]


@dataclass(frozen=True)
class PushOutcome:
    """단일 todo push 시도의 결과 — 워커가 이 값으로 finalize 방법을 결정한다.

    result_gid: push_success 시 반영할 Google event id.
    newly_created: 이번 시도에서 새로 만든 이벤트인지 — finalize 가 race 로 실패(0행)할 때
      orphan(중복) 정리 대상 판단에 사용(gid_at_claim 과 다른 새 이벤트만 삭제).
    """
    kind: PushKind
    result_gid: str | None = None
    newly_created: bool = False


def _recurrence_rule_to_rrule(rule: RecurrenceRule) -> str:
    """RecurrenceRule → Google RRULE 문자열."""
    freq = "DAILY" if rule.unit == "day" else "WEEKLY"
    parts = [f"RRULE:FREQ={freq};INTERVAL={rule.interval}"]
    if rule.until:
        # GCal UNTIL 형식: YYYYMMDD (date-only)
        until_compact = rule.until.replace("-", "")
        parts[0] += f";UNTIL={until_compact}"
    return parts[0]


class CalendarPushService:
    """todo 하나를 Google Calendar 에 반영하는 순수 API 로직 (DB/트랜잭션 없음).

    claim/heartbeat/finalize 등 상태 전이는 워커(트랜잭션 소유자)가 담당하고,
    이 서비스는 access_token + claim 된 Todo 를 받아 Google 호출만 수행한다.
    """

    def __init__(self, api_client: GoogleCalendarApiClient) -> None:
        self._api = api_client

    async def push_one(self, access_token: str, todo: Todo) -> PushOutcome:
        if todo.push_intent == "delete":
            return await self._delete(access_token, todo)
        # exception row (series_id non-null) → instance patch 경로
        if todo.series_id and todo.master_google_event_id and todo.original_start_time:
            return await self._push_exception_instance(access_token, todo)
        return await self._push(access_token, todo)

    async def _delete(self, access_token: str, todo: Todo) -> PushOutcome:
        # google_event_id 없으면 만든 적 없는 것 — 삭제 없이 성공 처리(완전 unlink).
        if todo.google_event_id:
            await self._api.delete_event(access_token, todo.google_event_id)
        return PushOutcome(kind="delete_success")

    async def _push(self, access_token: str, todo: Todo) -> PushOutcome:
        ev = self._to_write(todo)
        gid_at_claim = todo.google_event_id

        if gid_at_claim:
            updated_id = await self._api.update_event(access_token, gid_at_claim, ev)
            if updated_id is not None:
                return PushOutcome("push_success", result_gid=updated_id, newly_created=False)
            # 404 → 이벤트가 Google 에서 사라짐(직접 삭제/이동). 아래 create fallback.

        # gid 없음 또는 update 404 → 우선 archiveTodoId 로 기존 이벤트 재조회(중복 방지).
        # (create 성공 후 finalize 전 크래시 → 재시도 중복 생성 윈도우 차단)
        existing = await self._api.find_event_id_by_archive_todo_id(access_token, todo.id)
        if existing is not None:
            return PushOutcome("push_success", result_gid=existing, newly_created=False)

        created_id = await self._api.create_event(access_token, ev)
        return PushOutcome("push_success", result_gid=created_id, newly_created=True)

    async def _push_exception_instance(self, access_token: str, todo: Todo) -> PushOutcome:
        """반복 시리즈 exception row → GCal instance PATCH.

        GCal instance ID = "{master_event_id}_{originalStartTimeUTC}" 형식.
        base event 가 GCal 에 push 되어 있어야 이 경로가 의미 있다.
        """
        instance_id = build_gcal_instance_id(
            todo.master_google_event_id,  # type: ignore[arg-type]
            todo.original_start_time,  # type: ignore[arg-type]
        )
        ev = self._to_write(todo)
        updated_id = await self._api.patch_instance(access_token, instance_id, ev)
        if updated_id is not None:
            return PushOutcome("push_success", result_gid=updated_id, newly_created=False)
        # instance 없음 → 일반 create fallback (base 가 아직 push 안 됐을 수 있음)
        existing = await self._api.find_event_id_by_archive_todo_id(access_token, todo.id)
        if existing is not None:
            return PushOutcome("push_success", result_gid=existing, newly_created=False)
        created_id = await self._api.create_event(access_token, ev)
        return PushOutcome("push_success", result_gid=created_id, newly_created=True)

    def _to_write(self, todo: Todo) -> CalendarEventWrite:
        recurrence = None
        if todo.is_series_base and todo.recurrence_rule:
            recurrence = _recurrence_rule_to_rrule(todo.recurrence_rule)
        return CalendarEventWrite(
            archive_todo_id=todo.id,
            title=todo.title,
            description=todo.description or None,
            date_key=todo.date_key,
            start_at=todo.start_time,
            end_at=todo.end_time,
            timezone=todo.timezone,
            recurrence=recurrence,
        )
