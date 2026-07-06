from app.todo.application.dtos.commands import UNSET, UpdateTodoCommand
from app.todo.domain.exceptions.exceptions import TodoNotFoundException
from app.todo.domain.models.todo import Todo
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.domain.repositories.repository import ITodoRepository


class UpdateTodoUseCase:
    def __init__(self, todo_repo: ITodoRepository) -> None:
        self._todo_repo = todo_repo

    async def execute(self, cmd: UpdateTodoCommand) -> Todo:
        todo = await self._todo_repo.find_by_id(cmd.id, cmd.user_id)
        if not todo:
            raise TodoNotFoundException()

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

        # sentinel 기반: 키가 전송된 경우에만 갱신 (None 도 적용 = clear)
        if cmd.start_time is not UNSET:
            todo.start_time = cmd.start_time  # type: ignore[assignment]
        if cmd.end_time is not UNSET:
            todo.end_time = cmd.end_time  # type: ignore[assignment]
        if cmd.timezone is not UNSET:
            todo.timezone = cmd.timezone  # type: ignore[assignment]

        # 캘린더 연동된 todo(삭제 진행 중 제외)는 콘텐츠 변경을 Google 에 재반영.
        # push 상태 전이는 콘텐츠 save(merge)와 분리된 타겟 SQL 로 처리 —
        # mark_for_push 가 sync_attempt_id 를 NULL 로 무효화해 진행 중이던 워커
        # finalize 가 이 편집을 덮어쓰지 못하게 한다(lost-update 방지).
        re_push = todo.calendar_push_status is not None and todo.push_intent != "delete"

        saved = await self._todo_repo.save(todo)

        if re_push:
            await self._todo_repo.mark_for_push(saved.id, cmd.user_id)
            saved.calendar_push_status = "pending"
            saved.push_intent = "push"
        return saved
