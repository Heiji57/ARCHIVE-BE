from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.retrospective.domain.models.summary_template import UserSummaryTemplate
from app.retrospective.domain.models.value_objects import SummaryType
from app.retrospective.domain.repositories.repository import (
    IUserSummaryTemplateRepository,
)
from app.retrospective.infrastructure.persistence.models.summary_template_model import (
    UserSummaryTemplateModel,
)


class UserSummaryTemplateRepository(IUserSummaryTemplateRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, template: UserSummaryTemplate) -> UserSummaryTemplate:
        model = self._to_model(template)
        merged = await self._session.merge(model)
        await self._session.flush()
        return self._to_entity(merged)

    async def find_by_id(self, id: str, user_id: str) -> UserSummaryTemplate | None:
        result = await self._session.execute(
            select(UserSummaryTemplateModel).where(
                UserSummaryTemplateModel.id == id,
                UserSummaryTemplateModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def find_by_user_and_type(
        self, user_id: str, summary_type: SummaryType
    ) -> list[UserSummaryTemplate]:
        result = await self._session.execute(
            select(UserSummaryTemplateModel)
            .where(
                UserSummaryTemplateModel.user_id == user_id,
                UserSummaryTemplateModel.summary_type == summary_type.value,
            )
            .order_by(UserSummaryTemplateModel.created_at.asc())
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_by_name(
        self, user_id: str, summary_type: SummaryType, name: str
    ) -> UserSummaryTemplate | None:
        result = await self._session.execute(
            select(UserSummaryTemplateModel).where(
                UserSummaryTemplateModel.user_id == user_id,
                UserSummaryTemplateModel.summary_type == summary_type.value,
                UserSummaryTemplateModel.name == name,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def count_by_user_and_type(
        self, user_id: str, summary_type: SummaryType
    ) -> int:
        result = await self._session.execute(
            select(func.count(UserSummaryTemplateModel.id)).where(
                UserSummaryTemplateModel.user_id == user_id,
                UserSummaryTemplateModel.summary_type == summary_type.value,
            )
        )
        return int(result.scalar() or 0)

    async def delete(self, id: str, user_id: str) -> None:
        result = await self._session.execute(
            select(UserSummaryTemplateModel).where(
                UserSummaryTemplateModel.id == id,
                UserSummaryTemplateModel.user_id == user_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    def _to_model(self, entity: UserSummaryTemplate) -> UserSummaryTemplateModel:
        return UserSummaryTemplateModel(
            id=entity.id,
            user_id=entity.user_id,
            summary_type=entity.summary_type.value,
            name=entity.name,
            content=entity.content,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _to_entity(self, model: UserSummaryTemplateModel) -> UserSummaryTemplate:
        return UserSummaryTemplate(
            id=model.id,
            user_id=model.user_id,
            summary_type=SummaryType(model.summary_type),
            name=model.name,
            content=model.content,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
