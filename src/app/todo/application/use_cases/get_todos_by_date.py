from app.todo.application.dtos.queries import GetTodosByDateQuery
from app.todo.domain.models.todo import Todo
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.domain.repositories.repository import ITodoRepository
from app.todo.domain.utils.recurrence import generate_slots_from, make_virtual


class GetTodosByDateUseCase:
    def __init__(self, todo_repo: ITodoRepository) -> None:
        self._todo_repo = todo_repo

    async def execute(self, query: GetTodosByDateQuery) -> list[Todo]:
        date_key = query.date_key
        user_id = query.user_id

        # 1. 일반 todo (base row 제외됨 — repo 필터)
        todos = await self._todo_repo.find_by_date_key(user_id, date_key)

        # 2. 반복 확장
        masters = await self._todo_repo.find_masters_overlapping(user_id, date_key, date_key)
        if not masters:
            return todos

        series_ids = [m.id for m in masters]
        exceptions = await self._todo_repo.find_exceptions_batch(
            user_id, series_ids, date_key, date_key
        )
        exc_map: dict[tuple[str, str], Todo] = {
            (e.series_id, e.original_date_key): e  # type: ignore[index]
            for e in exceptions
        }

        expanded: list[Todo] = []
        for master in masters:
            slots = generate_slots_from(
                master.recurrence_rule,  # type: ignore[arg-type]
                master.date_key,
                date_key,
                date_key,
            )
            for slot in slots:
                exc = exc_map.get((master.id, slot))
                if exc is not None:
                    if exc.status != TaskStatus.CANCELLED:
                        expanded.append(exc)
                else:
                    expanded.append(make_virtual(master, slot))

        return todos + expanded
