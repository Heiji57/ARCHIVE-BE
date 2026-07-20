from app.retrospective.application.dtos.folder_commands import DeleteFolderCommand
from app.retrospective.domain.exceptions.exceptions import FolderNotFoundException
from app.retrospective.domain.repositories.repository import IFolderRepository


class DeleteFolderUseCase:
    """DELETE /folders/:id — 폴더만 삭제, 내용물(하위 폴더/회고록)은 삭제하지 않는다.

    하위 폴더의 parent_folder_id, 안의 회고록의 folder_id 는 DB FK(ON DELETE
    SET NULL)로 자동 해제되어 최상위로 orphan 된다 — 애플리케이션 레벨 재연결 없음.
    """

    def __init__(self, folder_repo: IFolderRepository) -> None:
        self._folder_repo = folder_repo

    async def execute(self, cmd: DeleteFolderCommand) -> None:
        folder = await self._folder_repo.find_by_id(cmd.folder_id, cmd.user_id)
        if folder is None:
            raise FolderNotFoundException()
        await self._folder_repo.delete(cmd.folder_id, cmd.user_id)
