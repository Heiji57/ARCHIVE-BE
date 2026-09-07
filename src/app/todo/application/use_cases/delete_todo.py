from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.shared.domain.utils.id import generate_id
from app.todo.domain.exceptions.exceptions import TodoNotFoundException
from app.todo.domain.models.todo import RecurrenceRule, Todo
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.domain.repositories.repository import ITodoRepository
from app.todo.domain.utils.recurrence import (
    build_gcal_instance_id,
    compute_instance_start,
    is_virtual_id,
    parse_virtual_id,
)


@dataclass(frozen=True)
class TodoDeleteOutcome:
    """삭제 후 라우터가 enqueue 해야 할 캘린더 task 신호.

    delete_google_event_id: best-effort 단건 삭제 대상(전체/슬롯 삭제 시).
    push_todo_id: 재푸시(재동기화) 대상 todo id — "following" 으로 시리즈의
    until 만 truncate 됐을 때, 단축된 RRULE 을 Google 에 반영하려면 삭제가
    아니라 push 가 필요하다.
    """
    delete_google_event_id: str | None = None
    push_todo_id: str | None = None


class DeleteTodoUseCase:
    def __init__(self, todo_repo: ITodoRepository) -> None:
        self._todo_repo = todo_repo

    async def execute(
        self, todo_id: str, user_id: str, recurrence_scope: str = "this"
    ) -> TodoDeleteOutcome:
        """todo 삭제 후, 라우터가 enqueue 해야 할 캘린더 task 신호를 반환한다.

        반복 Todo:
          - "this"      : 해당 슬롯만 취소(exception row CANCELLED 생성 또는 삭제)
          - "following" : 해당 슬롯 이후 전체 삭제 (base until 조정)
          - "all"       : 시리즈 전체 삭제 (base + 모든 exception)
        """
        if is_virtual_id(todo_id):
            return await self._delete_virtual(todo_id, user_id, recurrence_scope)

        todo = await self._todo_repo.find_by_id(todo_id, user_id)
        if not todo:
            raise TodoNotFoundException()

        if todo.is_series_base:
            if recurrence_scope == "all":
                return await self._delete_all(todo, user_id)
            if recurrence_scope == "following":
                # base 자체가 첫 슬롯 → 전체 삭제와 동일
                return await self._delete_all(todo, user_id)
            # "this" on base → base 의 첫 슬롯만 취소
            return await self._cancel_slot(todo, todo.date_key, user_id)

        if todo.series_id:
            # 실체화된 exception row
            if recurrence_scope == "all":
                master = await self._todo_repo.find_series_base(todo.series_id, user_id)
                if master:
                    return await self._delete_all(master, user_id)
            if recurrence_scope == "following":
                master = await self._todo_repo.find_series_base(todo.series_id, user_id)
                if master:
                    return await self._delete_following(
                        master, todo.original_date_key or todo.date_key, user_id
                    )
            # "this" — exception row 자체 삭제
            gid = todo.google_event_id
            await self._todo_repo.delete(todo.id, user_id)
            return TodoDeleteOutcome(delete_google_event_id=gid)

        # 일반(비반복) todo
        gid = todo.google_event_id
        await self._todo_repo.delete(todo_id, user_id)
        return TodoDeleteOutcome(delete_google_event_id=gid)

    # ── 가상 인스턴스 삭제 ──────────────────────────────────────────────────────

    async def _delete_virtual(
        self, todo_id: str, user_id: str, scope: str
    ) -> TodoDeleteOutcome:
        base_id, slot_date = parse_virtual_id(todo_id)
        master = await self._todo_repo.find_series_base(base_id, user_id)
        if not master:
            raise TodoNotFoundException()

        if scope == "all":
            return await self._delete_all(master, user_id)
        if scope == "following":
            return await self._delete_following(master, slot_date, user_id)
        # "this" — 해당 슬롯 CANCELLED exception 생성
        return await self._cancel_slot(master, slot_date, user_id)

    # ── "this" — 슬롯 취소 ─────────────────────────────────────────────────────

    async def _cancel_slot(self, master: Todo, slot_date: str, user_id: str) -> TodoDeleteOutcome:
        """해당 슬롯을 CANCELLED exception row 로 실체화한다.

        master 가 GCal 에 연동된 반복 이벤트라면, 해당 인스턴스 GCal ID 를 반환해
        라우터가 best-effort 삭제 task 를 enqueue 하도록 한다.
        """
        now = datetime.now(timezone.utc)
        inst_start = compute_instance_start(master.start_time, master.date_key, slot_date)
        cancel_exc = Todo(
            id=generate_id("todo"),
            user_id=user_id,
            title=master.title,
            status=TaskStatus.CANCELLED,
            date_key=slot_date,
            description=master.description,
            start_time=inst_start,
            end_time=None,
            timezone=master.timezone,
            created_at=now,
            updated_at=now,
            series_id=master.id,
            original_date_key=slot_date,
            original_start_time=inst_start,
            master_google_event_id=master.google_event_id,
        )
        await self._todo_repo.upsert_exception(cancel_exc)

        # GCal-linked 시리즈 → 해당 인스턴스 GCal ID 를 반환 (라우터가 삭제 enqueue)
        if master.google_event_id:
            return TodoDeleteOutcome(
                delete_google_event_id=build_gcal_instance_id(
                    master.google_event_id,
                    inst_start,
                    slot_date,
                )
            )
        return TodoDeleteOutcome()

    # ── "all" — 시리즈 전체 삭제 ───────────────────────────────────────────────

    async def _delete_all(self, master: Todo, user_id: str) -> TodoDeleteOutcome:
        await self._todo_repo.delete_all_exceptions(master.id, user_id)
        gid = master.google_event_id
        await self._todo_repo.delete(master.id, user_id)
        return TodoDeleteOutcome(delete_google_event_id=gid)

    # ── "following" — 해당 슬롯 이후 삭제 ─────────────────────────────────────

    async def _delete_following(
        self, master: Todo, from_slot: str, user_id: str
    ) -> TodoDeleteOutcome:
        # from_slot 이 base.date_key 와 같거나 이전이면 전체 삭제
        if from_slot <= master.date_key:
            return await self._delete_all(master, user_id)

        # from_slot 이전날로 until 조정
        prev_date = (date.fromisoformat(from_slot) - timedelta(days=1)).isoformat()
        old_rule = master.recurrence_rule
        if old_rule:
            new_until = prev_date if (old_rule.until is None or old_rule.until > prev_date) else old_rule.until
            master.recurrence_rule = RecurrenceRule(
                unit=old_rule.unit, interval=old_rule.interval, until=new_until
            )
            await self._todo_repo.save(master)

        # from_slot 이후 exception row 삭제
        await self._todo_repo.delete_exceptions_from(master.id, user_id, from_slot)

        # GCal-linked 시리즈라면 단축된 RRULE(UNTIL) 을 반영하도록 재푸시 예약.
        re_push = master.calendar_push_status is not None and master.push_intent != "delete"
        if re_push:
            await self._todo_repo.mark_for_push(master.id, user_id)
            return TodoDeleteOutcome(push_todo_id=master.id)
        return TodoDeleteOutcome()
