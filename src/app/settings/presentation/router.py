from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, status

from app.auth.presentation.requests.requests import (
    UpdateCountryRequest,
    UpdateTimezoneRequest,
)
from app.auth.presentation.responses.responses import UserResponse
from app.settings.application.dtos.commands import UpdateSettingsCommand
from app.settings.application.use_cases.get_settings import GetSettingsUseCase
from app.settings.application.use_cases.list_country_timezones import (
    ListCountryTimezonesUseCase,
)
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
from app.settings.presentation.responses.country_responses import (
    CountryTimezonesResponse,
)
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
            calendar_auto_push_todo=body.calendar_auto_push_todo,
            calendar_auto_delete_todo=body.calendar_auto_delete_todo,
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
            timezone=body.timezone,
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


@router.get(
    "/countries/{code}/timezones",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[CountryTimezonesResponse],
)
async def list_country_timezones(
    code: str,
    use_case: FromDishka[ListCountryTimezonesUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[CountryTimezonesResponse]:
    """국가의 IANA timezone 옵션 조회 (CLDR/pytz 기반).

    FE 사용 패턴: 사용자가 country 선택 → 이 endpoint 로 옵션 받아
    드롭다운 채움 → `multi: true` 면 사용자가 timezone 도 선택해야 함.
    """
    result = await use_case.execute(code)
    return ApiResponse.ok(CountryTimezonesResponse.from_result(result))
