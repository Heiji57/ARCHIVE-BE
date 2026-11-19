from app.retrospective.application.dtos.folder_commands import DeleteFolderCommand
from app.retrospective.domain.exceptions.exceptions import FolderNotFoundException
from app.retrospective.domain.repositories.repository import (
    IFolderRepository,
    IJournalEntryRepository,
)


class DeleteFolderUseCase:
    """DELETE /folders/:id — 폴더를 지우고, 바로 안의 회고는 휴지통으로 보낸다.

    폴더 자체는 휴지통에 넣지 않는다. 하위 폴더는 DB FK(ON DELETE SET NULL)로 최상위가
    된다. 휴지통에 간 회고의 folder_id 도 FK 로 비므로, 되살리면 "미분류"로 돌아온다.
    """

    def __init__(self, folder_repo: IFolderRepository, entry_repo: IJournalEntryRepository) -> None:
        self._folder_repo = folder_repo
        self._entry_repo = entry_repo

    async def execute(self, cmd: DeleteFolderCommand) -> None:
        folder = await self._folder_repo.find_by_id(cmd.folder_id, cmd.user_id)
        if folder is None:
            raise FolderNotFoundException()
        await self._entry_repo.soft_delete_in_folders(cmd.user_id, [cmd.folder_id])
        await self._folder_repo.delete(cmd.folder_id, cmd.user_id)
