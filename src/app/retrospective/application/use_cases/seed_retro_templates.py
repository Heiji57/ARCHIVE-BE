"""회원가입/OAuth 온보딩 시 사용자별 기본 회고 템플릿 4종을 시드한다."""
from datetime import datetime, timezone

from app.retrospective.domain.constants.retro_template_defaults import DEFAULT_CONTENT, DEFAULT_NAMES
from app.retrospective.domain.models.retro_template import RetroTemplate
from app.retrospective.domain.models.value_objects import RetroType
from app.retrospective.domain.repositories.repository import IRetroTemplateRepository
from app.settings.domain.models.user_settings import UserSettings
from app.settings.domain.repositories.repository import IUserSettingsRepository
from app.shared.domain.utils.id import generate_id


class SeedRetroTemplatesUseCase:
    def __init__(
        self,
        template_repo: IRetroTemplateRepository,
        settings_repo: IUserSettingsRepository,
    ) -> None:
        self._template_repo = template_repo
        self._settings_repo = settings_repo

    async def execute(self, user_id: str) -> None:
        now = datetime.now(timezone.utc)
        active_ids: dict[str, str] = {}

        for retro_type in RetroType:
            template = RetroTemplate(
                id=generate_id("tmpl"),
                user_id=user_id,
                retro_type=retro_type,
                name=DEFAULT_NAMES[retro_type],
                content=DEFAULT_CONTENT[retro_type],
                is_default=True,
                created_at=now,
            )
            saved = await self._template_repo.save(template)
            active_ids[retro_type.value] = saved.id

        settings = await self._settings_repo.find_by_user_id(user_id)
        if settings is None:
            settings = UserSettings.default(user_id)

        settings.active_retro_template_ids = active_ids
        settings.updated_at = now
        await self._settings_repo.save(settings)
