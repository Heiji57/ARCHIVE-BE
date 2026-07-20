from datetime import datetime, timezone

from app.shared.domain.utils.id import generate_id
from app.todo.application.dtos.commands import UNSET, UpdateTodoCommand
from app.todo.domain.exceptions.exceptions import TodoNotFoundException
from app.todo.domain.models.todo import Todo
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.domain.repositories.repository import ITodoRepository
from app.todo.domain.utils.recurrence import (
    compute_instance_start,
    compute_instance_end,
    generate_slots_from,
    is_virtual_id,
    make_virtual,
    parse_virtual_id,
)


class UpdateTodoUseCase:
    def __init__(self, todo_repo: ITodoRepository) -> None:
        self._todo_repo = todo_repo

    async def execute(self, cmd: UpdateTodoCommand) -> Todo:
        if is_virtual_id(cmd.id):
            return await self._update_virtual(cmd)
        todo = await self._todo_repo.find_by_id(cmd.id, cmd.user_id)
        if not todo:
            raise TodoNotFoundException()
        if todo.is_series_base:
            return await self._update_base(todo, cmd)
        # 일반 exception row 또는 일반 todo
        return await self._update_real(todo, cmd)

    # ── 가상 인스턴스 (DB 미저장) → 실체화 후 수정 ─────────────────────────────

    async def _update_virtual(self, cmd: UpdateTodoCommand) -> Todo:
        base_id, slot_date = parse_virtual_id(cmd.id)
        master = await self._todo_repo.find_series_base(base_id, cmd.user_id)
        if not master:
            raise TodoNotFoundException()

        scope = cmd.recurrence_scope
        if scope == "all":
            # base 자체를 수정
            return await self._update_base(master, cmd)
        if scope == "following":
            return await self._update_following(master, slot_date, cmd)
        # "this" — exception row 생성/수정
        return await self._materialize_and_update(master, slot_date, cmd)

    async def _materialize_and_update(
        self, master: Todo, slot_date: str, cmd: UpdateTodoCommand
    ) -> Todo:
        """가상 슬롯 → exception row 생성 후 패치 적용."""
        now = datetime.now(timezone.utc)
        inst_start = compute_instance_start(master.start_time, master.date_key, slot_date)
        inst_end = compute_instance_end(master.end_time, master.date_key, slot_date)
        exc = Todo(
            id=generate_id("todo"),
            user_id=master.user_id,
            title=master.title,
            status=master.status,
            date_key=slot_date,
            description=master.description,
            start_time=inst_start,
            end_time=inst_end,
            timezone=master.timezone,
            created_at=now,
            updated_at=now,
            recurrence_rule=None,
            series_id=master.id,
            original_date_key=slot_date,
            original_start_time=inst_start,
            master_google_event_id=master.google_event_id,
        )
        self._apply_patch(exc, cmd)
        return await self._todo_repo.upsert_exception(exc)

    # ── "following" scope — 시리즈 분리 ────────────────────────────────────────

    async def _update_following(self, master: Todo, from_slot: str, cmd: UpdateTodoCommand) -> Todo:
        """from_slot 이후를 새 시리즈로 분리.

        1. 기존 base 의 until 을 from_slot 전날로 설정.
        2. 기존 exception row 중 from_slot 이후 것은 새 base 로 이전.
        3. 새 base 생성 후 패치 적용.
        """
        from app.todo.domain.models.todo import RecurrenceRule
        from datetime import date, timedelta

        prev_date = (date.fromisoformat(from_slot) - timedelta(days=1)).isoformat()

        # 기존 base until 을 truncate
        old_rule = master.recurrence_rule
        if old_rule:
            new_until = prev_date if (old_rule.until is None or old_rule.until > prev_date) else old_rule.until
            master.recurrence_rule = RecurrenceRule(
                unit=old_rule.unit, interval=old_rule.interval, until=new_until
            )
        await self._todo_repo.save(master)

        # from_slot 이후 exception row 삭제 (새 base 로 재생성)
        await self._todo_repo.delete_exceptions_from(master.id, master.user_id, from_slot)

        # 새 base 생성
        now = datetime.now(timezone.utc)
        new_start = compute_instance_start(master.start_time, master.date_key, from_slot)
        new_end = compute_instance_end(master.end_time, master.date_key, from_slot)
        new_rule = RecurrenceRule(
            unit=master.recurrence_rule.unit if master.recurrence_rule else (old_rule.unit if old_rule else "day"),
            interval=master.recurrence_rule.interval if master.recurrence_rule else (old_rule.interval if old_rule else 1),
            until=None,
        )
        if cmd.recurrence_rule:
            new_rule = cmd.recurrence_rule

        new_base = Todo(
            id=generate_id("todo"),
            user_id=master.user_id,
            title=master.title,
            status=master.status,
            date_key=from_slot,
            description=master.description,
            start_time=new_start,
            end_time=new_end,
            timezone=master.timezone,
            created_at=now,
            updated_at=now,
            recurrence_rule=new_rule,
        )
        self._apply_patch(new_base, cmd)
        return await self._todo_repo.save(new_base)

    # ── base event 수정 ─────────────────────────────────────────────────────────

    async def _update_base(self, todo: Todo, cmd: UpdateTodoCommand) -> Todo:
        if cmd.recurrence_rule is not None:
            todo.recurrence_rule = cmd.recurrence_rule
        self._apply_patch(todo, cmd)
        re_push = todo.calendar_push_status is not None and todo.push_intent != "delete"
        saved = await self._todo_repo.save(todo)
        if re_push:
            await self._todo_repo.mark_for_push(saved.id, cmd.user_id)
            saved.calendar_push_status = "pending"
            saved.push_intent = "push"
        return saved

    # ── 실제 DB row (exception 또는 일반 todo) 수정 ─────────────────────────────

    async def _update_real(self, todo: Todo, cmd: UpdateTodoCommand) -> Todo:
        # 일반 todo(series_id 없음)에 recurrence_rule 이 오면 반복 시리즈 base 로 전환한다
        # (is_series_base = recurrence_rule 존재 AND series_id 없음 → 자동 충족).
        # 이미 다른 시리즈의 예외 row(series_id 있음)는 대상에서 제외 — 그 경우는
        # 가상 인스턴스의 "following" 분리 흐름(_update_following)을 써야 한다.
        if cmd.recurrence_rule is not None and todo.series_id is None:
            todo.recurrence_rule = cmd.recurrence_rule
        self._apply_patch(todo, cmd)
        re_push = todo.calendar_push_status is not None and todo.push_intent != "delete"
        saved = await self._todo_repo.save(todo)
        if re_push:
            await self._todo_repo.mark_for_push(saved.id, cmd.user_id)
            saved.calendar_push_status = "pending"
            saved.push_intent = "push"
        return saved

    # ── 공통 패치 헬퍼 ─────────────────────────────────────────────────────────

    def _apply_patch(self, todo: Todo, cmd: UpdateTodoCommand) -> None:
        if cmd.title is not None:
            todo.title = cmd.title
        if cmd.description is not None:
            todo.description = cmd.description
        if cmd.date_key is not None:
            todo.move_to(cmd.date_key)
        if cmd.status is not None:
            new_status = TaskStatus(cmd.status)
            if new_status == TaskStatus.DONE:
                todo.complete()
            elif new_status == TaskStatus.IN_PROGRESS:
                todo.start()
            else:
                todo.status = TaskStatus.NOT_START
        if cmd.start_time is not UNSET:
            todo.start_time = cmd.start_time  # type: ignore[assignment]
        if cmd.end_time is not UNSET:
            todo.end_time = cmd.end_time  # type: ignore[assignment]
        if cmd.timezone is not UNSET:
            todo.timezone = cmd.timezone  # type: ignore[assignment]
