from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, status

from app.settings.application.dtos.commands import UpdateSettingsCommand
from app.settings.application.use_cases.get_settings import GetSettingsUseCase
from app.settings.application.use_cases.update_settings import UpdateSettingsUseCase
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
        )
    )
    return ApiResponse.ok(SettingsResponse.from_entity(settings))
