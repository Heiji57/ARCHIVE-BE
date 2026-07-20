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
from app.google_calendar.domain.repositories.repository import ICalendarEventRepository
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
from app.shared.presentation.validators import parse_date_range

router = APIRouter(prefix="/calendar", tags=["calendar"], route_class=DishkaRoute)

_MAX_DATE_RANGE_DAYS = 62  # 두 달


def _validate_date_range(from_date: str, to_date: str) -> None:
    """from~to 범위가 최대 62일(두 달)을 초과하면 422.

    from/to 는 이 라우터에서 Query(...) 로 필수지만, FastAPI 는 빈 문자열("")도 값이
    없다고 보지 않고 그대로 통과시킨다. parse_date_range 는 빈 문자열을 falsy 로 보고
    None 을 반환하므로(다른 optional 호출부를 위한 설계), 여기서는 그 None 을 언패킹
    하기 전에 먼저 걸러 422 로 변환한다.
    """
    from fastapi import HTTPException

    if not from_date or not to_date:
        raise HTTPException(status_code=422, detail="날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).")

    f, t = parse_date_range(from_date, to_date, _MAX_DATE_RANGE_DAYS)
    if t < f:
        raise HTTPException(status_code=422, detail="to 는 from 보다 크거나 같아야 합니다.")


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
        user_id = await use_case.execute(code=code, state=state)
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

    # 연결/재연결 직후 즉시 pull-sync + push 사이클 재구동 — 다음 beat tick 을 기다리지
    # 않고 밀린 push(재연결 시 failed 재개 포함)를 곧바로 처리.
    from app.worker.tasks.sync_calendars import sync_user_calendar_task

    sync_user_calendar_task.apply_async(args=[user_id], queue="calendar")

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
    response_model=ApiResponse[list[CalendarEventResponse]],
)
async def sync(
    sync_use_case: FromDishka[SyncCalendarEventsUseCase],
    event_repo: FromDishka[ICalendarEventRepository],
    current_user: UserContext = Depends(get_current_user),
    from_date: str = Query(alias="from"),
    to_date: str = Query(alias="to"),
) -> ApiResponse[list[CalendarEventResponse]]:
    """수동 강제 동기화 후 지정 범위의 캘린더 이벤트만 반환.

    FE 는 sync 결과로 캘린더 이벤트 패널만 교체하면 되고, todos 는 별도 재요청 불필요.
    from/to 는 현재 FE 가 보고 있는 뷰의 날짜 범위를 넘긴다. 최대 62일 범위 허용.
    """
    _validate_date_range(from_date, to_date)
    await sync_use_case.execute(current_user.id, force=True)
    events = await event_repo.find_by_date_range(current_user.id, from_date, to_date)
    return ApiResponse.ok([CalendarEventResponse.from_entity(e) for e in events])


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
    _validate_date_range(from_date, to_date)
    events = await use_case.execute(current_user.id, from_date, to_date)
    return ApiResponse.ok([CalendarEventResponse.from_entity(e) for e in events])
