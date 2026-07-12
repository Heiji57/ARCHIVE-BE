from datetime import datetime, timezone

from app.retrospective.application.dtos.folder_commands import CreateFolderCommand
from app.retrospective.domain.exceptions.exceptions import (
    FolderNameDuplicatedException,
    FolderNotFoundException,
)
from app.retrospective.domain.models.folder import Folder
from app.retrospective.domain.repositories.repository import IFolderRepository
from app.shared.domain.utils.id import generate_id


class CreateFolderUseCase:
    def __init__(self, folder_repo: IFolderRepository) -> None:
        self._folder_repo = folder_repo

    async def execute(self, cmd: CreateFolderCommand) -> Folder:
        if cmd.parent_folder_id is not None:
            parent = await self._folder_repo.find_by_id(cmd.parent_folder_id, cmd.user_id)
            if parent is None:
                raise FolderNotFoundException()

        if await self._folder_repo.find_by_name(cmd.user_id, cmd.parent_folder_id, cmd.name):
            raise FolderNameDuplicatedException()

        now = datetime.now(timezone.utc)
        folder = Folder(
            id=generate_id("folder"),
            user_id=cmd.user_id,
            name=cmd.name,
            parent_folder_id=cmd.parent_folder_id,
            created_at=now,
        )
        return await self._folder_repo.save(folder)
