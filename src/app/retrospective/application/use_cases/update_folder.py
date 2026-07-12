from datetime import datetime, timezone

from app.retrospective.application.dtos.folder_commands import UNSET, UpdateFolderCommand
from app.retrospective.domain.exceptions.exceptions import (
    FolderCircularReferenceException,
    FolderNameDuplicatedException,
    FolderNotFoundException,
)
from app.retrospective.domain.models.folder import Folder
from app.retrospective.domain.repositories.repository import IFolderRepository


class UpdateFolderUseCase:
    """PATCH /folders/:id — 이름 변경 및/또는 이동(부모 변경).

    parent_folder_id 는 sentinel(UNSET) 로 미전송/명시 구분 — 명시적 null 은
    최상위로 이동, 미전송은 부모 그대로 유지.
    """

    def __init__(self, folder_repo: IFolderRepository) -> None:
        self._folder_repo = folder_repo

    async def execute(self, cmd: UpdateFolderCommand) -> Folder:
        folder = await self._folder_repo.find_by_id(cmd.folder_id, cmd.user_id)
        if folder is None:
            raise FolderNotFoundException()

        new_name = cmd.name if cmd.name is not None else folder.name
        new_parent_id = (
            folder.parent_folder_id if cmd.parent_folder_id is UNSET else cmd.parent_folder_id
        )

        if new_parent_id != folder.parent_folder_id:
            await self._validate_new_parent(folder, new_parent_id, cmd.user_id)

        if new_name != folder.name or new_parent_id != folder.parent_folder_id:
            duplicate = await self._folder_repo.find_by_name(cmd.user_id, new_parent_id, new_name)
            if duplicate is not None and duplicate.id != folder.id:
                raise FolderNameDuplicatedException()

        folder.name = new_name
        folder.parent_folder_id = new_parent_id
        folder.updated_at = datetime.now(timezone.utc)
        return await self._folder_repo.save(folder)

    async def _validate_new_parent(
        self, folder: Folder, new_parent_id: str | None, user_id: str
    ) -> None:
        if new_parent_id is None:
            return
        if new_parent_id == folder.id:
            raise FolderCircularReferenceException()

        parent = await self._folder_repo.find_by_id(new_parent_id, user_id)
        if parent is None:
            raise FolderNotFoundException()

        # new_parent 의 조상 체인에 folder 자신이 있으면, folder 는 new_parent 의
        # 상위(조상)라는 뜻 — 그 아래로 옮기면 순환이 생긴다.
        ancestors = await self._folder_repo.find_ancestors(new_parent_id, user_id)
        if any(a.id == folder.id for a in ancestors):
            raise FolderCircularReferenceException()
