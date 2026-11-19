"""사용자 캘린더(개인·팀·스터디). Google 연동(`/calendar/*`)과 이름이 겹치지 않게 `/calendars`.

캘린더를 화면에서 "끄는" 것은 보기 설정이라 서버에 두지 않는다(FE 로컬 저장).
"""

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, status

from app.calendars.application.use_cases.calendars import (
    CreateCalendarUseCase,
    DeleteCalendarUseCase,
    ListCalendarsUseCase,
    UpdateCalendarCommand,
    UpdateCalendarUseCase,
)
from app.calendars.presentation.requests.requests import (
    CreateCalendarRequest,
    UpdateCalendarRequest,
)
from app.calendars.presentation.responses.responses import CalendarResponse
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.presentation.schemas.response import ApiResponse

router = APIRouter(prefix="/calendars", tags=["calendars"], route_class=DishkaRoute)


@router.get("", response_model=ApiResponse[list[CalendarResponse]])
async def list_calendars(
    use_case: FromDishka[ListCalendarsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[list[CalendarResponse]]:
    calendars = await use_case.execute(current_user.id)
    return ApiResponse.ok([CalendarResponse.from_entity(c) for c in calendars])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[CalendarResponse])
async def create_calendar(
    body: CreateCalendarRequest,
    use_case: FromDishka[CreateCalendarUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[CalendarResponse]:
    calendar = await use_case.execute(current_user.id, body.name, body.color)
    return ApiResponse.created(CalendarResponse.from_entity(calendar))


@router.patch("/{calendar_id}", response_model=ApiResponse[CalendarResponse])
async def update_calendar(
    calendar_id: str,
    body: UpdateCalendarRequest,
    use_case: FromDishka[UpdateCalendarUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[CalendarResponse]:
    provided = {k: getattr(body, k) for k in body.model_fields_set if getattr(body, k) is not None}
    calendar = await use_case.execute(
        UpdateCalendarCommand(user_id=current_user.id, calendar_id=calendar_id, **provided)
    )
    return ApiResponse.ok(CalendarResponse.from_entity(calendar))


@router.delete("/{calendar_id}", response_model=ApiResponse[None])
async def delete_calendar(
    calendar_id: str,
    use_case: FromDishka[DeleteCalendarUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    """기본 캘린더는 409. 그 캘린더의 할 일은 기본 캘린더로 옮겨진다."""
    await use_case.execute(current_user.id, calendar_id)
    return ApiResponse.ok(None)
