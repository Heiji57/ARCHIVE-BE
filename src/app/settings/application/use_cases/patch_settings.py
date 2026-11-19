import json
from datetime import UTC, datetime

from app.github.domain.exceptions.exceptions import GitHubRepositoryNotLinkedException
from app.github.domain.repositories.repository import IGitHubRepositoryRepository
from app.settings.application.dtos.commands import PatchSettingsCommand
from app.settings.domain.exceptions.exceptions import SettingsUiPrefsTooLargeException
from app.settings.domain.models.user_settings import UserSettings
from app.settings.domain.repositories.repository import IUserSettingsRepository
from app.shared.domain.utils.unset import _Unset

# command 필드 → 엔티티 속성 (이름 동일). github push 대상은 검증이 필요해 따로 처리.
_PLAIN_FIELDS = (
    "locale",
    "auto_summary_weekly",
    "auto_summary_monthly",
    "auto_summary_yearly",
    "notification_retention_days",
    "calendar_auto_push_todo",
    "calendar_auto_delete_todo",
    "week_start",
    "work_schedule",
    "default_todo_minutes",
    "day_end_reminder",
    "quiet_hours",
    "email_digest",
)
UI_PREFERENCES_MAX_BYTES = 8 * 1024


class PatchSettingsUseCase:
    def __init__(
        self,
        repo: IUserSettingsRepository,
        github_repo: IGitHubRepositoryRepository,
    ) -> None:
        self._repo = repo
        self._github_repo = github_repo

    async def execute(self, cmd: PatchSettingsCommand) -> UserSettings:
        settings = await self._repo.find_by_user_id(cmd.user_id)
        if settings is None:
            settings = UserSettings.default(cmd.user_id)

        for name in _PLAIN_FIELDS:
            value = getattr(cmd, name)
            if not isinstance(value, _Unset):
                setattr(settings, name, value)

        if not isinstance(cmd.notification_prefs, _Unset):
            settings.notification_prefs = settings.notification_prefs.merged(cmd.notification_prefs)

        if not isinstance(cmd.ui_preferences, _Unset):
            merged = {**settings.ui_preferences, **cmd.ui_preferences}
            merged = {k: v for k, v in merged.items() if v is not None}
            if len(json.dumps(merged, ensure_ascii=False).encode()) > UI_PREFERENCES_MAX_BYTES:
                raise SettingsUiPrefsTooLargeException(
                    f"uiPreferences must be at most {UI_PREFERENCES_MAX_BYTES} bytes."
                )
            settings.ui_preferences = merged

        target_id = cmd.github_push_target_repository_id
        if not isinstance(target_id, _Unset):
            # push target 은 해당 user 에게 연결된 repository 여야 한다. None 은 해제.
            if target_id is not None:
                target = await self._github_repo.find_by_id(target_id, cmd.user_id)
                if target is None:
                    raise GitHubRepositoryNotLinkedException(
                        "Push target must be a linked repository."
                    )
            settings.github_push_target_repository_id = target_id

        settings.updated_at = datetime.now(UTC)
        return await self._repo.save(settings)
