from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi.exceptions import RequestValidationError

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


@dataclass(frozen=True)
class UpdateTodoOutcome:
    """수정 결과 + 라우터가 추가로 enqueue 해야 할 캘린더 push 신호.

    todo: 응답으로 내려갈 엔티티 (기존 execute() 반환값과 동일).
    extra_push_todo_id: `todo`와 별개로 재푸시가 필요한 todo id — "following" 분리 시
    옛 base(master)의 until 이 truncate 되어 GCal-linked 라면, 응답은 새로 분리된
    base(todo)로 나가지만 재푸시는 옛 master 쪽에 필요하다.
    """
    todo: Todo
    extra_push_todo_id: str | None = None


class UpdateTodoUseCase:
    def __init__(self, todo_repo: ITodoRepository) -> None:
        self._todo_repo = todo_repo

    async def execute(self, cmd: UpdateTodoCommand) -> UpdateTodoOutcome:
        if is_virtual_id(cmd.id):
            return await self._update_virtual(cmd)
        todo = await self._todo_repo.find_by_id(cmd.id, cmd.user_id)
        if not todo:
            raise TodoNotFoundException()
        if todo.is_series_base:
            return UpdateTodoOutcome(todo=await self._update_base(todo, cmd))
        if todo.series_id and cmd.recurrence_scope in ("following", "all"):
            master = await self._todo_repo.find_series_base(todo.series_id, cmd.user_id)
            if master:
                if cmd.recurrence_scope == "following":
                    return await self._update_following(
                        master, todo.original_date_key or todo.date_key, cmd, source=todo
                    )
                else:  # "all" — master 를 직접 업데이트해 전체 시리즈에 반영
                    saved = await self._update_base(master, cmd)
                    await self._todo_repo.delete_all_exceptions(master.id, cmd.user_id)
                    return UpdateTodoOutcome(todo=saved)
        # 일반 exception row 또는 일반 todo
        return UpdateTodoOutcome(todo=await self._update_real(todo, cmd))

    # ── 가상 인스턴스 (DB 미저장) → 실체화 후 수정 ─────────────────────────────

    async def _update_virtual(self, cmd: UpdateTodoCommand) -> UpdateTodoOutcome:
        base_id, slot_date = parse_virtual_id(cmd.id)
        master = await self._todo_repo.find_series_base(base_id, cmd.user_id)
        if not master:
            raise TodoNotFoundException()

        scope = cmd.recurrence_scope
        if scope == "all":
            saved = await self._update_base(master, cmd)
            await self._todo_repo.delete_all_exceptions(master.id, cmd.user_id)
            return UpdateTodoOutcome(todo=saved)
        if scope == "following":
            return await self._update_following(master, slot_date, cmd)
        # "this" — exception row 생성/수정
        return UpdateTodoOutcome(todo=await self._materialize_and_update(master, slot_date, cmd))

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
            tags=master.tags,
            due_date_key=master.due_date_key,
        )
        self._apply_patch(exc, cmd)
        return await self._todo_repo.upsert_exception(exc)

    # ── "following" scope — 시리즈 분리 ────────────────────────────────────────

    async def _update_following(
        self,
        master: Todo,
        from_slot: str,
        cmd: UpdateTodoCommand,
        source: Todo | None = None,
    ) -> UpdateTodoOutcome:
        """from_slot 이후를 새 시리즈로 분리.

        1. 기존 base 의 until 을 from_slot 전날로 설정.
        2. 기존 exception row 중 from_slot 이후 것은 새 base 로 이전.
        3. 새 base 생성 후 패치 적용.

        source: 새 base 의 콘텐츠(title/description/status/timezone/tags/start_time/
        end_time) baseline. 가상 인스턴스에서 분리할 땐 None → master 를 그대로 투영한다
        (compute_instance_start/end 로 슬롯에 맞게 시간 보정). 이미 실체화된 예외 row 에서
        분리할 땐 그 row 자신을 넘긴다 — master 대신 써야 그 회차가 이미 갖고 있던
        개별 수정 내용(예: 이전에 "this" 스코프로 바꾼 시간)을 분리 과정에서 잃지 않는다.
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

        # GCal-linked 시리즈라면 단축된 RRULE(UNTIL) 을 옛 base 에 반영하도록 재푸시 예약.
        # 응답은 새로 분리된 base 로 나가므로(아래 new_base), 옛 master 의 push 는
        # extra_push_todo_id 로 별도 신호해 라우터가 즉시 enqueue 하게 한다.
        extra_push_todo_id: str | None = None
        if master.calendar_push_status is not None and master.push_intent != "delete":
            await self._todo_repo.mark_for_push(master.id, master.user_id)
            extra_push_todo_id = master.id

        # from_slot 이후 exception row 삭제 (source 가 그중 하나였다면 함께 삭제됨) — 새 base 로 재생성
        await self._todo_repo.delete_exceptions_from(master.id, master.user_id, from_slot)

        # 새 base 생성
        now = datetime.now(timezone.utc)
        if source is not None:
            new_start, new_end = source.start_time, source.end_time
        else:
            new_start = compute_instance_start(master.start_time, master.date_key, from_slot)
            new_end = compute_instance_end(master.end_time, master.date_key, from_slot)
        field_source = source or master
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
            title=field_source.title,
            status=TaskStatus.NOT_START,
            date_key=from_slot,
            description=field_source.description,
            start_time=new_start,
            end_time=new_end,
            timezone=field_source.timezone,
            created_at=now,
            updated_at=now,
            recurrence_rule=new_rule,
            tags=field_source.tags,
            due_date_key=field_source.due_date_key,
        )
        self._apply_patch(new_base, cmd)
        saved = await self._todo_repo.save(new_base)
        return UpdateTodoOutcome(todo=saved, extra_push_todo_id=extra_push_todo_id)

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
                todo.completed_at = None
        if cmd.start_time is not UNSET:
            todo.start_time = cmd.start_time  # type: ignore[assignment]
        if cmd.end_time is not UNSET:
            todo.end_time = cmd.end_time  # type: ignore[assignment]
        if cmd.timezone is not UNSET:
            todo.timezone = cmd.timezone  # type: ignore[assignment]
        if cmd.tags is not UNSET:
            todo.tags = cmd.tags  # type: ignore[assignment]
        if cmd.due_date_key is not UNSET:
            if cmd.due_date_key is not None and cmd.due_date_key < todo.date_key:
                raise RequestValidationError(
                    errors=[{
                        "type": "value_error",
                        "loc": ("body", "due_date_key"),
                        "msg": "due_date_key must be >= date_key",
                        "input": cmd.due_date_key,
                        "ctx": {"error": "due_date_key must be >= date_key"},
                    }]
                )
            todo.due_date_key = cmd.due_date_key  # type: ignore[assignment]
