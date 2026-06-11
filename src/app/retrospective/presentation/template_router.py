"""사용자 AI 요약 템플릿 CRUD + 활성 선택.

마운트 경로: `/summaries/templates` + `/settings/auto-summary/active`
"""
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query, status

from app.retrospective.application.dtos.template_commands import (
    CreateSummaryTemplateCommand,
    DeleteSummaryTemplateCommand,
    SetActiveSummaryTemplateCommand,
    UpdateSummaryTemplateCommand,
)
from app.retrospective.application.use_cases.create_summary_template import (
    CreateSummaryTemplateUseCase,
)
from app.retrospective.application.use_cases.delete_summary_template import (
    DeleteSummaryTemplateUseCase,
)
from app.retrospective.application.use_cases.get_summary_template import (
    GetSummaryTemplateUseCase,
)
from app.retrospective.application.use_cases.list_summary_templates import (
    ListSummaryTemplatesUseCase,
)
from app.retrospective.application.use_cases.set_active_summary_template import (
    SetActiveSummaryTemplateUseCase,
)
from app.retrospective.application.use_cases.update_summary_template import (
    UpdateSummaryTemplateUseCase,
)
from app.retrospective.domain.models.value_objects import SummaryType
from app.retrospective.presentation.requests.template_requests import (
    CreateSummaryTemplateRequest,
    SetActiveSummaryTemplatesRequest,
    UpdateSummaryTemplateRequest,
)
from app.retrospective.presentation.responses.template_responses import (
    SummaryTemplateResponse,
)
from app.settings.domain.repositories.repository import IUserSettingsRepository
from app.settings.presentation.responses.responses import SettingsResponse
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.presentation.schemas.response import ApiResponse

template_router = APIRouter(
    prefix="/summaries/templates", tags=["summary-templates"], route_class=DishkaRoute
)
active_router = APIRouter(
    prefix="/settings/auto-summary", tags=["summary-templates"], route_class=DishkaRoute
)


async def _active_id_for(
    settings_repo: IUserSettingsRepository, user_id: str, summary_type: SummaryType
) -> str | None:
    settings = await settings_repo.find_by_user_id(user_id)
    if settings is None:
        return None
    return settings.active_template_id_for(summary_type.value)


@template_router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[SummaryTemplateResponse]],
)
async def list_templates(
    use_case: FromDishka[ListSummaryTemplatesUseCase],
    settings_repo: FromDishka[IUserSettingsRepository],
    current_user: UserContext = Depends(get_current_user),
    summary_type: str = Query(alias="type"),
) -> ApiResponse[list[SummaryTemplateResponse]]:
    stype = SummaryType(summary_type)
    templates = await use_case.execute(current_user.id, stype)
    active_id = await _active_id_for(settings_repo, current_user.id, stype)
    return ApiResponse.ok([
        SummaryTemplateResponse.from_entity(t, is_active=(t.id == active_id))
        for t in templates
    ])


@template_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[SummaryTemplateResponse],
)
async def create_template(
    body: CreateSummaryTemplateRequest,
    use_case: FromDishka[CreateSummaryTemplateUseCase],
    settings_repo: FromDishka[IUserSettingsRepository],
    current_user: UserContext = Depends(get_current_user),
    summary_type: str = Query(alias="type"),
) -> ApiResponse[SummaryTemplateResponse]:
    stype = SummaryType(summary_type)
    template = await use_case.execute(
        CreateSummaryTemplateCommand(
            user_id=current_user.id,
            summary_type=stype,
            name=body.name,
            content=body.content,
        )
    )
    active_id = await _active_id_for(settings_repo, current_user.id, stype)
    return ApiResponse.created(
        SummaryTemplateResponse.from_entity(template, is_active=(template.id == active_id))
    )


@template_router.get(
    "/{template_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[SummaryTemplateResponse],
)
async def get_template(
    template_id: str,
    use_case: FromDishka[GetSummaryTemplateUseCase],
    settings_repo: FromDishka[IUserSettingsRepository],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[SummaryTemplateResponse]:
    template = await use_case.execute(template_id, current_user.id)
    active_id = await _active_id_for(settings_repo, current_user.id, template.summary_type)
    return ApiResponse.ok(
        SummaryTemplateResponse.from_entity(template, is_active=(template.id == active_id))
    )


@template_router.patch(
    "/{template_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[SummaryTemplateResponse],
)
async def update_template(
    template_id: str,
    body: UpdateSummaryTemplateRequest,
    use_case: FromDishka[UpdateSummaryTemplateUseCase],
    settings_repo: FromDishka[IUserSettingsRepository],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[SummaryTemplateResponse]:
    template = await use_case.execute(
        UpdateSummaryTemplateCommand(
            user_id=current_user.id,
            template_id=template_id,
            name=body.name,
            content=body.content,
        )
    )
    active_id = await _active_id_for(settings_repo, current_user.id, template.summary_type)
    return ApiResponse.ok(
        SummaryTemplateResponse.from_entity(template, is_active=(template.id == active_id))
    )


@template_router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_template(
    template_id: str,
    use_case: FromDishka[DeleteSummaryTemplateUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> None:
    await use_case.execute(
        DeleteSummaryTemplateCommand(user_id=current_user.id, template_id=template_id)
    )


@active_router.put(
    "/active",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[SettingsResponse],
)
async def set_active_templates(
    body: SetActiveSummaryTemplatesRequest,
    use_case: FromDishka[SetActiveSummaryTemplateUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[SettingsResponse]:
    settings = await use_case.execute(
        SetActiveSummaryTemplateCommand(
            user_id=current_user.id,
            selections=body.to_selections(),
        )
    )
    return ApiResponse.ok(SettingsResponse.from_entity(settings))
