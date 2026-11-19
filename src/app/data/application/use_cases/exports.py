"""내보내기(12 §2) — 요청·상태 조회. 파일 만들기는 worker.build_export."""

from dataclasses import replace
from datetime import UTC, datetime

from app.data.domain.exceptions.exceptions import (
    ExportDailyLimitException,
    ExportExpiredException,
    ExportInProgressException,
    ExportNotFoundException,
)
from app.data.domain.models.export import (
    EXPORT_DAILY_LIMIT,
    EXPORT_STUCK_AFTER,
    ExportFormat,
    ExportJob,
    ExportScope,
)
from app.data.domain.repositories.repository import IExportRepository
from app.shared.domain.utils.id import generate_id
from app.user.domain.repositories.repository import IUserRepository

_DAY_SECONDS = 86400


class RequestExportUseCase:
    def __init__(self, repo: IExportRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        user_id: str,
        scopes: list[ExportScope],
        fmt: ExportFormat,
        now: datetime | None = None,
    ) -> ExportJob:
        now = now or datetime.now(UTC)
        pending = await self._repo.find_pending(user_id)
        if pending is not None:
            if now - pending.created_at < EXPORT_STUCK_AFTER:
                raise ExportInProgressException()
            # 워커가 죽어 영원히 pending 인 작업이 새 요청을 막지 않게 — 실패로 닫는다.
            await self._repo.save(replace(pending, status="failed"))
        since = datetime.fromtimestamp(now.timestamp() - _DAY_SECONDS, UTC)
        if await self._repo.count_since(user_id, since) >= EXPORT_DAILY_LIMIT:
            raise ExportDailyLimitException(
                details=[{"limit": EXPORT_DAILY_LIMIT, "windowSeconds": _DAY_SECONDS}]
            )
        job = ExportJob(
            id=generate_id("exp"),
            user_id=user_id,
            scopes=list(dict.fromkeys(scopes)),
            format=fmt,
            status="pending",
            created_at=now,
        )
        await self._repo.add(job)
        return job


class GetExportUseCase:
    def __init__(self, repo: IExportRepository, user_repo: IUserRepository) -> None:
        self._repo = repo
        self._user_repo = user_repo

    async def execute(self, user_id: str, export_id: str, now: datetime | None = None) -> ExportJob:
        return _check(await self._repo.get(export_id, user_id), now)

    async def execute_by_id(self, export_id: str, now: datetime | None = None) -> ExportJob:
        """서명 토큰으로 이미 소유가 확인된 내려받기 경로. 지운 계정의 링크는 막는다."""
        job = _check(await self._repo.get(export_id), now)
        if await self._user_repo.find_by_id(job.user_id) is None:
            raise ExportNotFoundException()
        return job


def _check(job: ExportJob | None, now: datetime | None) -> ExportJob:
    if job is None:
        raise ExportNotFoundException()
    if job.is_expired(now or datetime.now(UTC)):
        raise ExportExpiredException()
    return job
