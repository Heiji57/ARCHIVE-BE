from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.domain.exceptions.exceptions import ExportInProgressException
from app.data.domain.models.export import ExportJob
from app.data.domain.repositories.repository import IExportRepository
from app.data.infrastructure.persistence.models.export_model import ExportModel
from app.shared.infrastructure.database.errors import translate_unique_violations

_UNIQUE_VIOLATIONS = {"uq_exports_user_pending": ExportInProgressException}


class ExportRepository(IExportRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, job: ExportJob) -> None:
        async with translate_unique_violations(_UNIQUE_VIOLATIONS):
            self._session.add(_to_model(job))
            await self._session.flush()

    async def get(self, export_id: str, user_id: str | None = None) -> ExportJob | None:
        stmt = select(ExportModel).where(ExportModel.id == export_id)
        if user_id is not None:
            stmt = stmt.where(ExportModel.user_id == user_id)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_entity(model) if model else None

    async def find_pending(self, user_id: str) -> ExportJob | None:
        model = (
            await self._session.execute(
                select(ExportModel).where(
                    ExportModel.user_id == user_id, ExportModel.status == "pending"
                )
            )
        ).scalar_one_or_none()
        return _to_entity(model) if model else None

    async def count_since(self, user_id: str, since: datetime) -> int:
        total = await self._session.scalar(
            select(func.count())
            .select_from(ExportModel)
            .where(ExportModel.user_id == user_id, ExportModel.created_at >= since)
        )
        return int(total or 0)

    async def save(self, job: ExportJob) -> None:
        await self._session.merge(_to_model(job))
        await self._session.flush()

    async def find_files_expired(self, now: datetime) -> list[ExportJob]:
        result = await self._session.execute(
            select(ExportModel).where(
                ExportModel.file_key.is_not(None), ExportModel.expires_at <= now
            )
        )
        return [_to_entity(m) for m in result.scalars()]

    async def file_keys_of(self, user_id: str) -> list[str]:
        result = await self._session.execute(
            select(ExportModel.file_key).where(
                ExportModel.user_id == user_id, ExportModel.file_key.is_not(None)
            )
        )
        return [k for k in result.scalars() if k]


def _to_model(job: ExportJob) -> ExportModel:
    return ExportModel(
        id=job.id,
        user_id=job.user_id,
        scopes=list(job.scopes),
        format=job.format,
        status=job.status,
        file_key=job.file_key,
        created_at=job.created_at,
        ready_at=job.ready_at,
        expires_at=job.expires_at,
    )


def _to_entity(m: ExportModel) -> ExportJob:
    return ExportJob(
        id=m.id,
        user_id=m.user_id,
        scopes=list(m.scopes),  # type: ignore[arg-type]
        format=m.format,  # type: ignore[arg-type]
        status=m.status,  # type: ignore[arg-type]
        created_at=m.created_at,
        file_key=m.file_key,
        ready_at=m.ready_at,
        expires_at=m.expires_at,
    )
