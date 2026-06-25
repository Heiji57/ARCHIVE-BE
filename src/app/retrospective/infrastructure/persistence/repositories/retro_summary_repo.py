from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import SummaryContent, SummaryStatus, SummaryType
from app.retrospective.domain.repositories.repository import IRetroSummaryRepository
from app.retrospective.infrastructure.persistence.models.retro_summary_model import RetroSummaryModel


class RetroSummaryRepository(IRetroSummaryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, summary: RetroSummary) -> RetroSummary:
        model = self._to_model(summary)
        merged = await self._session.merge(model)
        await self._session.flush()
        return self._to_entity(merged)

    async def find_by_id(self, id: str, user_id: str) -> RetroSummary | None:
        result = await self._session.execute(
            select(RetroSummaryModel).where(
                RetroSummaryModel.id == id, RetroSummaryModel.user_id == user_id
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def find_by_period(
        self,
        user_id: str,
        summary_type: SummaryType,
        period_start: date,
    ) -> RetroSummary | None:
        result = await self._session.execute(
            select(RetroSummaryModel).where(
                RetroSummaryModel.user_id == user_id,
                RetroSummaryModel.summary_type == summary_type.value,
                RetroSummaryModel.period_start == period_start,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def find_all_by_type(self, user_id: str, summary_type: SummaryType) -> list[RetroSummary]:
        result = await self._session.execute(
            select(RetroSummaryModel)
            .where(
                RetroSummaryModel.user_id == user_id,
                RetroSummaryModel.summary_type == summary_type.value,
            )
            .order_by(RetroSummaryModel.period_start.desc())
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_completed_in_range(
        self, user_id: str, summary_type: SummaryType, from_date: date, to_date: date
    ) -> list[RetroSummary]:
        result = await self._session.execute(
            select(RetroSummaryModel)
            .where(
                RetroSummaryModel.user_id == user_id,
                RetroSummaryModel.summary_type == summary_type.value,
                RetroSummaryModel.status == SummaryStatus.COMPLETED.value,
                RetroSummaryModel.period_start >= from_date,
                RetroSummaryModel.period_start <= to_date,
            )
            .order_by(RetroSummaryModel.period_start.asc())
        )
        return [self._to_entity(m) for m in result.scalars()]

    def _to_model(self, entity: RetroSummary) -> RetroSummaryModel:
        return RetroSummaryModel(
            id=entity.id,
            user_id=entity.user_id,
            summary_type=entity.summary_type.value,
            period_start=entity.period_start,
            period_end=entity.period_end,
            status=entity.status.value,
            content=entity.content.to_dict() if entity.content else None,
            edited_content=entity.edited_content,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _to_entity(self, model: RetroSummaryModel) -> RetroSummary:
        return RetroSummary(
            id=model.id,
            user_id=model.user_id,
            summary_type=SummaryType(model.summary_type),
            period_start=model.period_start,
            period_end=model.period_end,
            status=SummaryStatus(model.status),
            content=SummaryContent.from_dict(model.content) if model.content else None,
            edited_content=model.edited_content,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
