from datetime import date

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.settings.domain.models.preferences import (
    DayEndReminder,
    NotificationPrefs,
    QuietHours,
    WorkSchedule,
)
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

    async def mark_sent(self, user_id: str, **sent_dates: date) -> None:
        allowed = {"last_due_reminder_date", "last_day_end_reminder_date", "last_weekly_email_date"}
        if not sent_dates or set(sent_dates) - allowed:
            raise ValueError(f"mark_sent accepts only {sorted(allowed)}")
        await self._session.execute(
            update(UserSettingsModel)
            .where(UserSettingsModel.user_id == user_id)
            .values(**sent_dates)
        )

    def _to_model(self, entity: UserSettings) -> UserSettingsModel:
        return UserSettingsModel(
            user_id=entity.user_id,
            locale=entity.locale,
            auto_summary_weekly=entity.auto_summary_weekly,
            auto_summary_monthly=entity.auto_summary_monthly,
            auto_summary_yearly=entity.auto_summary_yearly,
            notification_retention_days=entity.notification_retention_days,
            calendar_auto_push_todo=entity.calendar_auto_push_todo,
            calendar_auto_delete_todo=entity.calendar_auto_delete_todo,
            last_summary_date_local=entity.last_summary_date_local,
            github_push_target_repository_id=entity.github_push_target_repository_id,
            active_summary_template_ids=dict(entity.active_summary_template_ids),
            active_retro_template_ids=dict(entity.active_retro_template_ids),
            week_start=entity.week_start,
            work_schedule=entity.work_schedule.to_dict(),
            default_todo_minutes=entity.default_todo_minutes,
            day_end_reminder=entity.day_end_reminder.to_dict(),
            notification_prefs=entity.notification_prefs.to_dict(),
            quiet_hours=entity.quiet_hours.to_dict(),
            email_digest=entity.email_digest,
            ui_preferences=dict(entity.ui_preferences),
            last_due_reminder_date=entity.last_due_reminder_date,
            last_day_end_reminder_date=entity.last_day_end_reminder_date,
            last_weekly_email_date=entity.last_weekly_email_date,
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
            calendar_auto_push_todo=model.calendar_auto_push_todo,
            calendar_auto_delete_todo=model.calendar_auto_delete_todo,
            last_summary_date_local=model.last_summary_date_local,
            github_push_target_repository_id=model.github_push_target_repository_id,
            active_summary_template_ids=dict(model.active_summary_template_ids or {}),
            active_retro_template_ids=dict(model.active_retro_template_ids or {}),
            week_start=model.week_start or "mon",  # type: ignore[arg-type]
            work_schedule=WorkSchedule.from_dict(model.work_schedule),
            default_todo_minutes=model.default_todo_minutes,
            day_end_reminder=DayEndReminder.from_dict(model.day_end_reminder),
            notification_prefs=NotificationPrefs.from_dict(model.notification_prefs),
            quiet_hours=QuietHours.from_dict(model.quiet_hours),
            email_digest=model.email_digest or "off",  # type: ignore[arg-type]
            ui_preferences=dict(model.ui_preferences or {}),
            last_due_reminder_date=model.last_due_reminder_date,
            last_day_end_reminder_date=model.last_day_end_reminder_date,
            last_weekly_email_date=model.last_weekly_email_date,
            updated_at=model.updated_at,
        )
