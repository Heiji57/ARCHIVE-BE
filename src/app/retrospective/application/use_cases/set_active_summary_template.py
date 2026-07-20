"""summary_type 별 활성 템플릿 ID 설정.

검증:
- template_id 가 None 이면 → 해당 summary_type 비활성화 (시스템 기본 사용)
- template_id 가 문자열이면:
  - 존재 + cmd.user_id 소유 + 해당 template 의 summary_type 이 키와 일치해야 함
  - 위반 시 SummaryTemplateNotFoundException (정보 노출 최소화 — 다른 user 의 ID 였든
    summary_type 불일치였든 동일 코드)

부분 갱신: cmd.selections 에 들어온 키만 갱신, 나머지 키는 user_settings 의 기존
값을 유지한다.
"""
from datetime import datetime, timezone

from app.retrospective.application.dtos.template_commands import (
    SetActiveSummaryTemplateCommand,
)
from app.retrospective.domain.exceptions.exceptions import (
    SummaryTemplateNotFoundException,
)
from app.retrospective.domain.models.value_objects import SummaryType
from app.retrospective.domain.repositories.repository import (
    IUserSummaryTemplateRepository,
)
from app.settings.domain.models.user_settings import UserSettings
from app.settings.domain.repositories.repository import IUserSettingsRepository


class SetActiveSummaryTemplateUseCase:
    def __init__(
        self,
        template_repo: IUserSummaryTemplateRepository,
        settings_repo: IUserSettingsRepository,
    ) -> None:
        self._template_repo = template_repo
        self._settings_repo = settings_repo

    async def execute(
        self, cmd: SetActiveSummaryTemplateCommand
    ) -> UserSettings:
        settings = await self._settings_repo.find_by_user_id(cmd.user_id)
        if settings is None:
            settings = UserSettings.default(cmd.user_id)

        for summary_type_key, template_id in cmd.selections.items():
            # 키 자체가 잘못된 summary_type 이면 무시
            try:
                summary_type = SummaryType(summary_type_key)
            except ValueError:
                continue

            if template_id is None:
                # 비활성화
                settings.active_summary_template_ids[summary_type.value] = None
                continue

            template = await self._template_repo.find_by_id(template_id, cmd.user_id)
            if template is None or template.summary_type != summary_type:
                raise SummaryTemplateNotFoundException()

            settings.active_summary_template_ids[summary_type.value] = template.id

        settings.updated_at = datetime.now(timezone.utc)
        return await self._settings_repo.save(settings)
