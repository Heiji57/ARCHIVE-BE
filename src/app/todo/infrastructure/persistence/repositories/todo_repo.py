from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.todo.domain.models.todo import Todo
from app.todo.domain.models.value_objects import TaskStatus
from app.todo.domain.repositories.repository import ITodoRepository
from app.todo.infrastructure.persistence.models.todo_model import TodoModel


class TodoRepository(ITodoRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, todo: Todo) -> Todo:
        model = self._to_model(todo)
        merged = await self._session.merge(model)
        await self._session.flush()
        return self._to_entity(merged)

    async def find_by_id(self, id: str, user_id: str) -> Todo | None:
        result = await self._session.execute(
            select(TodoModel).where(TodoModel.id == id, TodoModel.user_id == user_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def find_by_date_range(self, user_id: str, from_date: str, to_date: str) -> list[Todo]:
        result = await self._session.execute(
            select(TodoModel)
            .where(
                TodoModel.user_id == user_id,
                TodoModel.date_key >= from_date,
                TodoModel.date_key <= to_date,
            )
            .order_by(TodoModel.date_key, TodoModel.created_at)
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_by_date_key(self, user_id: str, date_key: str) -> list[Todo]:
        result = await self._session.execute(
            select(TodoModel)
            .where(TodoModel.user_id == user_id, TodoModel.date_key == date_key)
            .order_by(TodoModel.created_at)
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_by_full_text(
        self, user_id: str, query: str, page: int, size: int
    ) -> tuple[list[Todo], int]:
        stmt = (
            select(TodoModel)
            .where(TodoModel.user_id == user_id)
            .where(TodoModel.title_tsv.match(query))  # type: ignore[union-attr]
        )
        total = await self._session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        result = await self._session.execute(
            stmt.order_by(TodoModel.created_at.desc()).offset((page - 1) * size).limit(size)
        )
        return [self._to_entity(m) for m in result.scalars()], total or 0

    async def delete(self, id: str, user_id: str) -> None:
        model = await self._session.execute(
            select(TodoModel).where(TodoModel.id == id, TodoModel.user_id == user_id)
        )
        row = model.scalar_one_or_none()
        if row:
            await self._session.delete(row)

    def _to_model(self, entity: Todo) -> TodoModel:
        return TodoModel(
            id=entity.id,
            user_id=entity.user_id,
            title=entity.title,
            status=entity.status.value,
            date_key=entity.date_key,
            description=entity.description,
            start_time=entity.start_time,
            end_time=entity.end_time,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            completed_at=entity.completed_at,
        )

    def _to_entity(self, model: TodoModel) -> Todo:
        return Todo(
            id=model.id,
            user_id=model.user_id,
            title=model.title,
            status=TaskStatus(model.status),
            date_key=model.date_key,
            description=model.description,
            start_time=model.start_time,
            end_time=model.end_time,
            created_at=model.created_at,
            updated_at=model.updated_at,
            completed_at=model.completed_at,
        )
