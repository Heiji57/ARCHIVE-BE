from typing import Any

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import RedirectResponse

from app.auth.domain.exceptions.exceptions import AuthTokenInvalidException
from app.auth.presentation.requests.requests import (
    UpdateCountryRequest,
    UpdateTimezoneRequest,
)
from app.auth.presentation.responses.responses import UserResponse
from app.settings.application.dtos.commands import PatchSettingsCommand
from app.settings.application.use_cases.get_settings import GetSettingsUseCase
from app.settings.application.use_cases.list_country_timezones import (
    ListCountryTimezonesUseCase,
)
from app.settings.application.use_cases.patch_settings import PatchSettingsUseCase
from app.settings.application.use_cases.update_country import (
    UpdateCountryCommand,
    UpdateCountryUseCase,
)
from app.settings.application.use_cases.update_timezone import (
    UpdateTimezoneCommand,
    UpdateTimezoneUseCase,
)
from app.settings.presentation.requests.requests import (
    AutoSummarySettingsPatchRequest,
    CalendarSettingsPatchRequest,
    GeneralSettingsPatchRequest,
    GitHubSettingsPatchRequest,
    NotificationSettingsPatchRequest,
    UnsubscribeRequest,
    WorkSettingsPatchRequest,
)
from app.settings.presentation.responses.country_responses import (
    CountryTimezonesResponse,
)
from app.settings.presentation.responses.responses import SettingsResponse
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import decode_unsubscribe_token, get_current_user
from app.shared.infrastructure.config.settings import get_settings as get_app_config
from app.shared.presentation.schemas.response import ApiResponse
from app.user.domain.repositories.repository import IUserRepository

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


async def _patch(
    use_case: PatchSettingsUseCase, user_id: str, fields: dict[str, Any]
) -> ApiResponse[SettingsResponse]:
    settings = await use_case.execute(PatchSettingsCommand(user_id=user_id, **fields))
    return ApiResponse.ok(SettingsResponse.from_entity(settings))


@router.patch(
    "/general",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[SettingsResponse],
)
async def patch_general_settings(
    body: GeneralSettingsPatchRequest,
    use_case: FromDishka[PatchSettingsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[SettingsResponse]:
    return await _patch(use_case, current_user.id, body.provided())


@router.patch(
    "/auto-summary",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[SettingsResponse],
)
async def patch_auto_summary_settings(
    body: AutoSummarySettingsPatchRequest,
    use_case: FromDishka[PatchSettingsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[SettingsResponse]:
    return await _patch(use_case, current_user.id, body.provided())


@router.patch(
    "/notifications",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[SettingsResponse],
)
async def patch_notification_settings(
    body: NotificationSettingsPatchRequest,
    use_case: FromDishka[PatchSettingsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[SettingsResponse]:
    return await _patch(use_case, current_user.id, body.provided())


@router.patch(
    "/calendar",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[SettingsResponse],
)
async def patch_calendar_settings(
    body: CalendarSettingsPatchRequest,
    use_case: FromDishka[PatchSettingsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[SettingsResponse]:
    return await _patch(use_case, current_user.id, body.provided())


@router.patch(
    "/work",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[SettingsResponse],
)
async def patch_work_settings(
    body: WorkSettingsPatchRequest,
    use_case: FromDishka[PatchSettingsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[SettingsResponse]:
    return await _patch(use_case, current_user.id, body.provided())


@router.patch(
    "/github",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[SettingsResponse],
)
async def patch_github_settings(
    body: GitHubSettingsPatchRequest,
    use_case: FromDishka[PatchSettingsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[SettingsResponse]:
    fields = {f"github_{k}": v for k, v in body.provided().items()}
    return await _patch(use_case, current_user.id, fields)


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


@router.get("/email-digest/unsubscribe")
async def unsubscribe_email_digest_link(token: str = Query(min_length=1)) -> RedirectResponse:
    """주간 이메일의 수신 거부 링크. **상태를 바꾸지 않는다** — 메일 보안 스캐너가 링크를 미리
    열어도 구독이 풀리지 않게, FE 확인 화면으로 토큰을 넘기고 실제 해제는 POST 가 한다."""
    return RedirectResponse(
        f"{get_app_config().frontend_url}/unsubscribe?token={token}", status_code=303
    )


@router.post("/email-digest/unsubscribe", response_model=ApiResponse[None])
async def unsubscribe_email_digest(
    body: UnsubscribeRequest,
    use_case: FromDishka[PatchSettingsUseCase],
    user_repo: FromDishka[IUserRepository],
) -> ApiResponse[None]:
    """로그인 없이 서명 토큰으로 `email_digest = off`. 토큰 무효·만료·없는 사용자면 401."""
    user_id = decode_unsubscribe_token(body.token)
    if await user_repo.find_by_id(user_id) is None:
        raise AuthTokenInvalidException()
    await use_case.execute(PatchSettingsCommand(user_id=user_id, email_digest="off"))
    return ApiResponse.ok(None)
