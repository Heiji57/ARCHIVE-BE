from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.settings.domain.models.user_settings import UserSettings
from app.settings.domain.repositories.repository import IUserSettingsRepository
from app.settings.infrastructure.persistence.models.user_settings_model import UserSettingsModel


class UserSettingsRepository(IUserSettingsRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_user_id(self, user_id: str) -> UserSettings | None:
        result = await self._session.execute(
            select(UserSettingsModel).where(UserSettingsModel.user_id == user_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def save(self, settings: UserSettings) -> UserSettings:
        model = self._to_model(settings)
        merged = await self._session.merge(model)
        await self._session.flush()
        return self._to_entity(merged)

    def _to_model(self, entity: UserSettings) -> UserSettingsModel:
        return UserSettingsModel(
            user_id=entity.user_id,
            locale=entity.locale,
            auto_summary_weekly=entity.auto_summary_weekly,
            auto_summary_monthly=entity.auto_summary_monthly,
            auto_summary_yearly=entity.auto_summary_yearly,
            notification_retention_days=entity.notification_retention_days,
            last_schedule_check_at=entity.last_schedule_check_at,
            last_summary_date_local=entity.last_summary_date_local,
            github_push_target_repository_id=entity.github_push_target_repository_id,
            updated_at=entity.updated_at,
        )

    def _to_entity(self, model: UserSettingsModel) -> UserSettings:
        return UserSettings(
            user_id=model.user_id,
            locale=model.locale,
            auto_summary_weekly=model.auto_summary_weekly,
            auto_summary_monthly=model.auto_summary_monthly,
            auto_summary_yearly=model.auto_summary_yearly,
            notification_retention_days=model.notification_retention_days,
            last_schedule_check_at=model.last_schedule_check_at,
            last_summary_date_local=model.last_summary_date_local,
            github_push_target_repository_id=model.github_push_target_repository_id,
            updated_at=model.updated_at,
        )
