from datetime import datetime, timezone

from app.settings.domain.repositories.repository import IUserSettingsRepository
from app.shared.domain.utils.id import generate_id
from app.todo.application.dtos.commands import CreateTodoCommand
from app.todo.domain.models.todo import Todo
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.domain.repositories.repository import ITodoRepository


class CreateTodoUseCase:
    def __init__(
        self,
        todo_repo: ITodoRepository,
        settings_repo: IUserSettingsRepository,
    ) -> None:
        self._todo_repo = todo_repo
        self._settings_repo = settings_repo

    async def execute(self, cmd: CreateTodoCommand) -> Todo:
        now = datetime.now(timezone.utc)
        todo = Todo(
            id=generate_id("todo"),
            user_id=cmd.user_id,
            title=cmd.title,
            status=TaskStatus(cmd.status),
            date_key=cmd.date_key,
            description=cmd.description,
            start_time=cmd.start_time,
            end_time=cmd.end_time,
            timezone=cmd.timezone,
            created_at=now,
            recurrence_rule=cmd.recurrence_rule,
        )
        saved = await self._todo_repo.save(todo)

        # 캘린더 push 여부 결정: 명시값 우선, 없으면 사용자 기본 설정.
        if await self._should_push(cmd):
            await self._todo_repo.mark_for_push(saved.id, cmd.user_id)
            # 응답/라우터 enqueue 판단을 위해 in-memory 상태 반영.
            saved.calendar_push_status = "pending"
            saved.push_intent = "push"
        return saved

    async def _should_push(self, cmd: CreateTodoCommand) -> bool:
        if cmd.push_to_calendar is not None:
            return cmd.push_to_calendar
        settings = await self._settings_repo.find_by_user_id(cmd.user_id)
        return bool(settings and settings.calendar_auto_push_todo)
