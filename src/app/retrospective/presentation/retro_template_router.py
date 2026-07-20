from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query, status

from app.retrospective.application.dtos.retro_template_commands import (
    CreateRetroTemplateCommand,
    DeleteRetroTemplateCommand,
    ResetRetroTemplateCommand,
    SetActiveRetroTemplateCommand,
    UpdateRetroTemplateCommand,
)
from app.retrospective.application.use_cases.create_retro_template import CreateRetroTemplateUseCase
from app.retrospective.application.use_cases.delete_retro_template import DeleteRetroTemplateUseCase
from app.retrospective.application.use_cases.list_retro_templates import ListRetroTemplatesUseCase
from app.retrospective.application.use_cases.reset_retro_template import ResetRetroTemplateUseCase
from app.retrospective.application.use_cases.set_active_retro_template import SetActiveRetroTemplateUseCase
from app.retrospective.application.use_cases.update_retro_template import UpdateRetroTemplateUseCase
from app.retrospective.domain.models.value_objects import RetroType
from app.retrospective.presentation.requests.retro_template_requests import (
    CreateRetroTemplateRequest,
    SetActiveRetroTemplateRequest,
    UpdateRetroTemplateRequest,
)
from app.retrospective.presentation.responses.retro_template_responses import RetroTemplateResponse
from app.settings.domain.repositories.repository import IUserSettingsRepository
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.presentation.schemas.response import ApiResponse

router = APIRouter(prefix="/templates", tags=["retro-templates"], route_class=DishkaRoute)


async def _active_id_for(
    settings_repo: IUserSettingsRepository, user_id: str, retro_type: RetroType
) -> str | None:
    settings = await settings_repo.find_by_user_id(user_id)
    if settings is None:
        return None
    return settings.active_retro_template_id_for(retro_type.value)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[RetroTemplateResponse]],
)
async def list_templates(
    use_case: FromDishka[ListRetroTemplatesUseCase],
    settings_repo: FromDishka[IUserSettingsRepository],
    current_user: UserContext = Depends(get_current_user),
    retro_type: str | None = Query(default=None, alias="retro_type"),
) -> ApiResponse[list[RetroTemplateResponse]]:
    rtype = RetroType(retro_type) if retro_type else None
    templates = await use_case.execute(current_user.id, rtype)

    settings = await settings_repo.find_by_user_id(current_user.id)
    active_ids: dict[str, str | None] = (
        settings.active_retro_template_ids if settings else {}
    )
    return ApiResponse.ok([
        RetroTemplateResponse.from_entity(t, is_active=(t.id == active_ids.get(t.retro_type.value)))
        for t in templates
    ])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[RetroTemplateResponse],
)
async def create_template(
    body: CreateRetroTemplateRequest,
    use_case: FromDishka[CreateRetroTemplateUseCase],
    settings_repo: FromDishka[IUserSettingsRepository],
    current_user: UserContext = Depends(get_current_user),
    retro_type: str = Query(alias="retro_type"),
) -> ApiResponse[RetroTemplateResponse]:
    rtype = RetroType(retro_type)
    template = await use_case.execute(
        CreateRetroTemplateCommand(
            user_id=current_user.id,
            retro_type=rtype,
            name=body.name,
            content=body.content,
        )
    )
    active_id = await _active_id_for(settings_repo, current_user.id, rtype)
    return ApiResponse.created(
        RetroTemplateResponse.from_entity(template, is_active=(template.id == active_id))
    )


# PUT /templates/active — static path 먼저 선언해야 /{template_id} 보다 우선 매칭됨
@router.put(
    "/active",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[RetroTemplateResponse],
)
async def set_active_template(
    body: SetActiveRetroTemplateRequest,
    use_case: FromDishka[SetActiveRetroTemplateUseCase],
    template_repo_uc: FromDishka[ListRetroTemplatesUseCase],
    settings_repo: FromDishka[IUserSettingsRepository],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[RetroTemplateResponse]:
    rtype = RetroType(body.retro_type)
    await use_case.execute(
        SetActiveRetroTemplateCommand(
            user_id=current_user.id,
            retro_type=rtype,
            template_id=body.template_id,
        )
    )
    # 응답: 새로 활성이 된 템플릿 반환
    templates = await template_repo_uc.execute(current_user.id, rtype)
    target = next((t for t in templates if t.id == body.template_id), None)
    if target is None:
        from app.retrospective.domain.exceptions.exceptions import RetroTemplateNotFoundException
        raise RetroTemplateNotFoundException()
    return ApiResponse.ok(RetroTemplateResponse.from_entity(target, is_active=True))


@router.patch(
    "/{template_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[RetroTemplateResponse],
)
async def update_template(
    template_id: str,
    body: UpdateRetroTemplateRequest,
    use_case: FromDishka[UpdateRetroTemplateUseCase],
    settings_repo: FromDishka[IUserSettingsRepository],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[RetroTemplateResponse]:
    template = await use_case.execute(
        UpdateRetroTemplateCommand(
            user_id=current_user.id,
            template_id=template_id,
            name=body.name,
            content=body.content,
        )
    )
    active_id = await _active_id_for(settings_repo, current_user.id, template.retro_type)
    return ApiResponse.ok(
        RetroTemplateResponse.from_entity(template, is_active=(template.id == active_id))
    )


@router.post(
    "/{template_id}/reset",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[RetroTemplateResponse],
)
async def reset_template(
    template_id: str,
    use_case: FromDishka[ResetRetroTemplateUseCase],
    settings_repo: FromDishka[IUserSettingsRepository],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[RetroTemplateResponse]:
    template = await use_case.execute(
        ResetRetroTemplateCommand(user_id=current_user.id, template_id=template_id)
    )
    active_id = await _active_id_for(settings_repo, current_user.id, template.retro_type)
    return ApiResponse.ok(
        RetroTemplateResponse.from_entity(template, is_active=(template.id == active_id))
    )


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_template(
    template_id: str,
    use_case: FromDishka[DeleteRetroTemplateUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> None:
    await use_case.execute(
        DeleteRetroTemplateCommand(user_id=current_user.id, template_id=template_id)
    )
