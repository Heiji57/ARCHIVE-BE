from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, status

from app.auth.presentation.requests.requests import (
    UpdateCountryRequest,
    UpdateTimezoneRequest,
)
from app.auth.presentation.responses.responses import UserResponse
from app.settings.application.dtos.commands import UpdateSettingsCommand
from app.settings.application.use_cases.get_settings import GetSettingsUseCase
from app.settings.application.use_cases.update_country import (
    UpdateCountryCommand,
    UpdateCountryUseCase,
)
from app.settings.application.use_cases.update_settings import UpdateSettingsUseCase
from app.settings.application.use_cases.update_timezone import (
    UpdateTimezoneCommand,
    UpdateTimezoneUseCase,
)
from app.settings.presentation.requests.requests import UpdateSettingsRequest
from app.settings.presentation.responses.responses import SettingsResponse
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.presentation.schemas.response import ApiResponse

router = APIRouter(prefix="/settings", tags=["settings"], route_class=DishkaRoute)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[SettingsResponse],
)
async def get_settings(
    use_case: FromDishka[GetSettingsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[SettingsResponse]:
    settings = await use_case.execute(current_user.id)
    return ApiResponse.ok(SettingsResponse.from_entity(settings))


@router.put(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[SettingsResponse],
)
async def update_settings(
    body: UpdateSettingsRequest,
    use_case: FromDishka[UpdateSettingsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[SettingsResponse]:
    settings = await use_case.execute(
        UpdateSettingsCommand(
            user_id=current_user.id,
            locale=body.locale,
            auto_summary_weekly=body.auto_summary_weekly,
            auto_summary_monthly=body.auto_summary_monthly,
            auto_summary_yearly=body.auto_summary_yearly,
            notification_retention_days=body.notification_retention_days,
            last_schedule_check_at=body.last_schedule_check_at,
            github_push_target_repository_id=body.github.push_target_repository_id,
        )
    )
    return ApiResponse.ok(SettingsResponse.from_entity(settings))


@router.patch(
    "/country",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[UserResponse],
)
async def update_country(
    body: UpdateCountryRequest,
    use_case: FromDishka[UpdateCountryUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[UserResponse]:
    user = await use_case.execute(
        UpdateCountryCommand(
            user_id=current_user.id,
            country=body.country,
            region=body.region,
        )
    )
    return ApiResponse.ok(UserResponse.from_entity(user))


@router.patch(
    "/timezone",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[UserResponse],
)
async def update_timezone(
    body: UpdateTimezoneRequest,
    use_case: FromDishka[UpdateTimezoneUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[UserResponse]:
    user = await use_case.execute(
        UpdateTimezoneCommand(user_id=current_user.id, timezone=body.timezone)
    )
    return ApiResponse.ok(UserResponse.from_entity(user))
