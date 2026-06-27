import json

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import HTMLResponse

from app.google_calendar.application.use_cases.disconnect_calendar import (
    DisconnectCalendarUseCase,
)
from app.google_calendar.application.use_cases.get_calendar_events import (
    GetCalendarEventsUseCase,
)
from app.google_calendar.application.use_cases.get_connection_status import (
    GetCalendarConnectionStatusUseCase,
)
from app.google_calendar.application.use_cases.handle_calendar_callback import (
    HandleCalendarCallbackUseCase,
)
from app.google_calendar.application.use_cases.initiate_calendar_connect import (
    InitiateCalendarConnectUseCase,
)
from app.google_calendar.application.use_cases.sync_calendar_events import (
    SyncCalendarEventsUseCase,
)
from app.google_calendar.presentation.responses.responses import (
    CalendarConnectInitResponse,
    CalendarConnectionResponse,
    CalendarEventResponse,
)
from app.shared.domain.context.user_context import UserContext
from app.shared.domain.exceptions.base import BaseAppException
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.infrastructure.config.settings import get_settings
from app.shared.presentation.schemas.response import ApiResponse

router = APIRouter(prefix="/calendar", tags=["calendar"], route_class=DishkaRoute)


def _callback_html(message_type: str, frontend_origin: str, **extra: str) -> str:
    message = json.dumps({"type": message_type, **extra})
    origin = json.dumps(frontend_origin)
    return f"""<!DOCTYPE html>
<html><head><title>Google Calendar</title></head><body><script>
  if (window.opener) {{ window.opener.postMessage({message}, {origin}); window.close(); }}
  else {{ window.location.href = {origin}; }}
</script></body></html>"""


# ── Connection ───────────────────────────────────────────────────────────────

@router.get(
    "/connection",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[CalendarConnectionResponse],
)
async def get_connection(
    use_case: FromDishka[GetCalendarConnectionStatusUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[CalendarConnectionResponse]:
    status_data = await use_case.execute(current_user.id)
    return ApiResponse.ok(CalendarConnectionResponse.from_status(status_data))


@router.post(
    "/connect/init",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[CalendarConnectInitResponse],
)
async def connect_init(
    use_case: FromDishka[InitiateCalendarConnectUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[CalendarConnectInitResponse]:
    """캘린더 연결 시작. 응답 authorizeUrl 을 FE 가 popup 으로 연다."""
    authorize_url = await use_case.execute(current_user.id)
    return ApiResponse.ok(CalendarConnectInitResponse(authorize_url=authorize_url))


@router.get("/callback")
async def callback(
    use_case: FromDishka[HandleCalendarCallbackUseCase],
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> HTMLResponse:
    """Google OAuth callback — postMessage 로 FE 에 연결 결과 전달."""
    frontend_origin = get_settings().frontend_url

    if error or not code or not state:
        return HTMLResponse(
            content=_callback_html(
                "calendar_error", frontend_origin, error=error or "missing_params"
            )
        )

    try:
        await use_case.execute(code=code, state=state)
    except BaseAppException as e:
        return HTMLResponse(
            content=_callback_html("calendar_error", frontend_origin, error=e.code)
        )
    except Exception:
        return HTMLResponse(
            content=_callback_html(
                "calendar_error", frontend_origin, error="INTERNAL_ERROR"
            )
        )

    return HTMLResponse(content=_callback_html("calendar_connected", frontend_origin))


@router.delete(
    "/connection",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def disconnect(
    use_case: FromDishka[DisconnectCalendarUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    await use_case.execute(current_user.id)
    return ApiResponse.ok(None)


# ── Sync / Events ────────────────────────────────────────────────────────────

@router.post(
    "/sync",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[CalendarConnectionResponse],
)
async def sync(
    sync_use_case: FromDishka[SyncCalendarEventsUseCase],
    status_use_case: FromDishka[GetCalendarConnectionStatusUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[CalendarConnectionResponse]:
    """수동 강제 동기화 (staleness 무시)."""
    await sync_use_case.execute(current_user.id, force=True)
    status_data = await status_use_case.execute(current_user.id)
    return ApiResponse.ok(CalendarConnectionResponse.from_status(status_data))


@router.get(
    "/events",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[CalendarEventResponse]],
)
async def get_events(
    use_case: FromDishka[GetCalendarEventsUseCase],
    from_date: str = Query(alias="from"),
    to_date: str = Query(alias="to"),
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[list[CalendarEventResponse]]:
    events = await use_case.execute(current_user.id, from_date, to_date)
    return ApiResponse.ok([CalendarEventResponse.from_entity(e) for e in events])
