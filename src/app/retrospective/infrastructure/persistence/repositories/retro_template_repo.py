from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.retrospective.domain.models.retro_template import RetroTemplate
from app.retrospective.domain.models.value_objects import RetroType
from app.retrospective.domain.repositories.repository import IRetroTemplateRepository
from app.retrospective.infrastructure.persistence.models.retro_template_model import RetroTemplateModel


class RetroTemplateRepository(IRetroTemplateRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, template: RetroTemplate) -> RetroTemplate:
        model = self._to_model(template)
        merged = await self._session.merge(model)
        await self._session.flush()
        return self._to_entity(merged)

    async def find_by_id(self, id: str, user_id: str) -> RetroTemplate | None:
        result = await self._session.execute(
            select(RetroTemplateModel).where(
                RetroTemplateModel.id == id,
                RetroTemplateModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def find_by_user(self, user_id: str) -> list[RetroTemplate]:
        result = await self._session.execute(
            select(RetroTemplateModel)
            .where(RetroTemplateModel.user_id == user_id)
            .order_by(RetroTemplateModel.retro_type, RetroTemplateModel.created_at)
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_by_user_and_type(
        self, user_id: str, retro_type: RetroType
    ) -> list[RetroTemplate]:
        result = await self._session.execute(
            select(RetroTemplateModel)
            .where(
                RetroTemplateModel.user_id == user_id,
                RetroTemplateModel.retro_type == retro_type.value,
            )
            .order_by(RetroTemplateModel.created_at)
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_default_for_type(
        self, user_id: str, retro_type: RetroType
    ) -> RetroTemplate | None:
        result = await self._session.execute(
            select(RetroTemplateModel).where(
                RetroTemplateModel.user_id == user_id,
                RetroTemplateModel.retro_type == retro_type.value,
                RetroTemplateModel.is_default.is_(True),
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def find_by_name(
        self, user_id: str, retro_type: RetroType, name: str
    ) -> RetroTemplate | None:
        result = await self._session.execute(
            select(RetroTemplateModel).where(
                RetroTemplateModel.user_id == user_id,
                RetroTemplateModel.retro_type == retro_type.value,
                RetroTemplateModel.name == name,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def delete(self, id: str, user_id: str) -> None:
        result = await self._session.execute(
            select(RetroTemplateModel).where(
                RetroTemplateModel.id == id,
                RetroTemplateModel.user_id == user_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    def _to_model(self, entity: RetroTemplate) -> RetroTemplateModel:
        return RetroTemplateModel(
            id=entity.id,
            user_id=entity.user_id,
            retro_type=entity.retro_type.value,
            name=entity.name,
            content=entity.content,
            is_default=entity.is_default,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _to_entity(self, model: RetroTemplateModel) -> RetroTemplate:
        return RetroTemplate(
            id=model.id,
            user_id=model.user_id,
            retro_type=RetroType(model.retro_type),
            name=model.name,
            content=model.content,
            is_default=model.is_default,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
