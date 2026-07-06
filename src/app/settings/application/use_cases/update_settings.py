from datetime import datetime, timezone

from app.github.domain.exceptions.exceptions import GitHubRepositoryNotLinkedException
from app.github.domain.repositories.repository import IGitHubRepositoryRepository
from app.settings.application.dtos.commands import UpdateSettingsCommand
from app.settings.domain.models.user_settings import UserSettings
from app.settings.domain.repositories.repository import IUserSettingsRepository


class UpdateSettingsUseCase:
    def __init__(
        self,
        repo: IUserSettingsRepository,
        github_repo: IGitHubRepositoryRepository,
    ) -> None:
        self._repo = repo
        self._github_repo = github_repo

    async def execute(self, cmd: UpdateSettingsCommand) -> UserSettings:
        settings = await self._repo.find_by_user_id(cmd.user_id)
        if settings is None:
            settings = UserSettings.default(cmd.user_id)

        settings.locale = cmd.locale
        settings.auto_summary_weekly = cmd.auto_summary_weekly
        settings.auto_summary_monthly = cmd.auto_summary_monthly
        settings.auto_summary_yearly = cmd.auto_summary_yearly
        settings.notification_retention_days = cmd.notification_retention_days
        settings.calendar_auto_push_todo = cmd.calendar_auto_push_todo
        settings.last_schedule_check_at = cmd.last_schedule_check_at

        # push target 검증: 해당 user에게 연결된 repository여야 함
        if cmd.github_push_target_repository_id is not None:
            target = await self._github_repo.find_by_id(
                cmd.github_push_target_repository_id, cmd.user_id
            )
            if target is None:
                raise GitHubRepositoryNotLinkedException(
                    "Push target must be a linked repository."
                )
        settings.github_push_target_repository_id = cmd.github_push_target_repository_id
        settings.updated_at = datetime.now(timezone.utc)

        return await self._repo.save(settings)
