from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.retrospective.domain.models.retro_summary import RetroSummary
from app.retrospective.domain.models.value_objects import SummaryContent, SummaryStatus, SummaryType
from app.retrospective.domain.repositories.repository import IRetroSummaryRepository
from app.retrospective.infrastructure.persistence.models.folder_model import FolderModel  # noqa: F401
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

    async def find_by_periods(
        self,
        user_id: str,
        summary_type: SummaryType,
        period_starts: list[date],
    ) -> list[RetroSummary]:
        if not period_starts:
            return []
        result = await self._session.execute(
            select(RetroSummaryModel).where(
                RetroSummaryModel.user_id == user_id,
                RetroSummaryModel.summary_type == summary_type.value,
                RetroSummaryModel.period_start.in_(set(period_starts)),
            )
        )
        return [self._to_entity(m) for m in result.scalars()]

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

    async def find_page(
        self,
        user_id: str,
        summary_type: SummaryType | None,
        page: int,
        size: int,
        q: str | None,
        from_date: date | None,
        to_date: date | None,
    ) -> tuple[list[RetroSummary], int]:
        stmt = select(RetroSummaryModel).where(RetroSummaryModel.user_id == user_id)
        if summary_type is not None:
            stmt = stmt.where(RetroSummaryModel.summary_type == summary_type.value)
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(
                or_(
                    RetroSummaryModel.content.ilike(pattern),
                    RetroSummaryModel.edited_content.ilike(pattern),
                )
            )
        if from_date:
            stmt = stmt.where(RetroSummaryModel.period_end >= from_date)
        if to_date:
            stmt = stmt.where(RetroSummaryModel.period_start <= to_date)
        total = await self._session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        result = await self._session.execute(
            stmt.order_by(RetroSummaryModel.period_start.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return [self._to_entity(m) for m in result.scalars()], total or 0

    async def find_by_folder(
        self, user_id: str, folder_id: str | None, summary_type: SummaryType | None = None
    ) -> list[RetroSummary]:
        stmt = select(RetroSummaryModel).where(RetroSummaryModel.user_id == user_id)
        stmt = stmt.where(
            RetroSummaryModel.folder_id.is_(None)
            if folder_id is None
            else RetroSummaryModel.folder_id == folder_id
        )
        if summary_type:
            stmt = stmt.where(RetroSummaryModel.summary_type == summary_type.value)
        result = await self._session.execute(stmt.order_by(RetroSummaryModel.period_start.desc()))
        return [self._to_entity(m) for m in result.scalars()]

    async def count_by_folder_ids(
        self, user_id: str, folder_ids: list[str]
    ) -> dict[str, int]:
        if not folder_ids:
            return {}
        result = await self._session.execute(
            select(RetroSummaryModel.folder_id, func.count())
            .where(
                RetroSummaryModel.user_id == user_id,
                RetroSummaryModel.folder_id.in_(folder_ids),
            )
            .group_by(RetroSummaryModel.folder_id)
        )
        return {row[0]: row[1] for row in result.all()}

    def _to_model(self, entity: RetroSummary) -> RetroSummaryModel:
        return RetroSummaryModel(
            id=entity.id,
            user_id=entity.user_id,
            summary_type=entity.summary_type.value,
            period_start=entity.period_start,
            period_end=entity.period_end,
            status=entity.status.value,
            content=entity.content.text if entity.content else None,
            edited_content=entity.edited_content,
            folder_id=entity.folder_id,
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
            content=SummaryContent.from_text(model.content) if model.content else None,
            edited_content=model.edited_content,
            folder_id=model.folder_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
