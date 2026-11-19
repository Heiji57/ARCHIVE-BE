from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.application.use_cases.exports import GetExportUseCase, RequestExportUseCase
from app.data.application.use_cases.trash import TrashUseCase
from app.data.domain.repositories.repository import IExportRepository
from app.data.infrastructure.persistence.repositories.export_repo import ExportRepository
from app.retrospective.application.use_cases.entry_trash import EntryTrashUseCase
from app.todo.application.use_cases.trash import TodoTrashUseCase


class DataProvider(Provider):
    """data 모듈(휴지통·내보내기).

    종류별 휴지통 유스케이스는 각 모듈 것이지만 이 API 만 쓰므로 여기 등록.
    """

    scope = Scope.REQUEST

    @provide
    def export_repo(self, session: AsyncSession) -> IExportRepository:
        return ExportRepository(session)

    request_export = provide(RequestExportUseCase)
    get_export = provide(GetExportUseCase)
    todo_trash = provide(TodoTrashUseCase)
    entry_trash = provide(EntryTrashUseCase)
    trash = provide(TrashUseCase)
