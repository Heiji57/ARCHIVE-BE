from datetime import datetime, timezone

from app.retrospective.application.dtos.commands import CreateEntryCommand
from app.retrospective.domain.constants.entry_title_defaults import resolve_entry_title
from app.retrospective.domain.exceptions.exceptions import JournalEntryAlreadyExistsException
from app.retrospective.domain.models.journal_entry import JournalEntry
from app.retrospective.domain.models.value_objects import RetroType
from app.retrospective.domain.repositories.repository import IJournalEntryRepository
from app.settings.domain.repositories.repository import IUserSettingsRepository
from app.shared.domain.utils.id import generate_id


class CreateEntryUseCase:
    def __init__(
        self,
        entry_repo: IJournalEntryRepository,
        settings_repo: IUserSettingsRepository,
    ) -> None:
        self._entry_repo = entry_repo
        self._settings_repo = settings_repo

    async def execute(self, cmd: CreateEntryCommand) -> JournalEntry:
        existing = await self._entry_repo.find_by_date_key(cmd.user_id, cmd.date_key, cmd.retro_type)
        if existing:
            raise JournalEntryAlreadyExistsException()

        retro_type = RetroType(cmd.retro_type)
        title = cmd.title
        if not (title and title.strip()):
            settings = await self._settings_repo.find_by_user_id(cmd.user_id)
            title = resolve_entry_title(
                title, cmd.date_key, retro_type, settings.locale if settings else None
            )

        now = datetime.now(timezone.utc)
        entry = JournalEntry(
            id=generate_id("entry"),
            user_id=cmd.user_id,
            date_key=cmd.date_key,
            title=title,
            content=cmd.content,
            retro_type=retro_type,
            created_at=now,
        )
        return await self._entry_repo.save(entry)
