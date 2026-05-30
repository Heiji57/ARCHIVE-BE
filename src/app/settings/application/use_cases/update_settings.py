from datetime import datetime, timezone

from app.settings.application.dtos.commands import UpdateSettingsCommand
from app.settings.domain.models.user_settings import UserSettings
from app.settings.domain.repositories.repository import IUserSettingsRepository


class UpdateSettingsUseCase:
    def __init__(self, repo: IUserSettingsRepository) -> None:
        self._repo = repo

    async def execute(self, cmd: UpdateSettingsCommand) -> UserSettings:
        settings = await self._repo.find_by_user_id(cmd.user_id)
        if settings is None:
            settings = UserSettings.default(cmd.user_id)

        settings.locale = cmd.locale
        settings.auto_summary_weekly = cmd.auto_summary_weekly
        settings.auto_summary_monthly = cmd.auto_summary_monthly
        settings.auto_summary_yearly = cmd.auto_summary_yearly
        settings.notification_retention_days = cmd.notification_retention_days
        settings.last_schedule_check_at = cmd.last_schedule_check_at
        settings.updated_at = datetime.now(timezone.utc)

        return await self._repo.save(settings)
