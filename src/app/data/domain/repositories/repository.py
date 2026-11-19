from abc import ABC, abstractmethod
from datetime import datetime

from app.data.domain.models.export import ExportJob


class IExportRepository(ABC):
    @abstractmethod
    async def add(self, job: ExportJob) -> None:
        """진행 중(pending)이 이미 있으면 ExportInProgressException.

        동시 요청도 부분 유니크 인덱스로 막는다."""
        ...

    @abstractmethod
    async def get(self, export_id: str, user_id: str | None = None) -> ExportJob | None: ...

    @abstractmethod
    async def find_pending(self, user_id: str) -> ExportJob | None: ...

    @abstractmethod
    async def count_since(self, user_id: str, since: datetime) -> int: ...

    @abstractmethod
    async def save(self, job: ExportJob) -> None: ...

    @abstractmethod
    async def find_files_expired(self, now: datetime) -> list[ExportJob]:
        """파일이 남아 있는데 보관 기간이 지난 것."""
        ...

    @abstractmethod
    async def file_keys_of(self, user_id: str) -> list[str]:
        """계정 완전 삭제 때 지울 파일."""
        ...
