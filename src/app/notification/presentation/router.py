import asyncio
import json

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query, status
from sse_starlette.sse import EventSourceResponse

from app.notification.application.use_cases.delete_notification import DeleteNotificationUseCase
from app.notification.application.use_cases.delete_notifications import DeleteNotificationsUseCase
from app.notification.application.use_cases.get_notifications import GetNotificationsUseCase
from app.notification.application.use_cases.mark_all_as_read import MarkAllAsReadUseCase
from app.notification.application.use_cases.mark_as_read import MarkAsReadUseCase
from app.notification.presentation.responses.responses import NotificationResponse
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.infrastructure.config.settings import get_settings
from app.shared.presentation.schemas.response import ApiResponse

router = APIRouter(prefix="/notifications", tags=["notifications"], route_class=DishkaRoute)

_SSE_TIMEOUT = 300  # 5분


@router.get(
    "/stream",
    summary="알림 실시간 스트림 (SSE)",
)
async def notification_stream(
    current_user: UserContext = Depends(get_current_user),
) -> EventSourceResponse:
    settings = get_settings()

    async def generator():
        from redis.asyncio import Redis
        redis = Redis.from_url(settings.redis.cache_url, decode_responses=True)
        pubsub = redis.pubsub()
        channel = f"notifications:{current_user.id}"
        await pubsub.subscribe(channel)

        try:
            async with asyncio.timeout(_SSE_TIMEOUT):
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        yield {"data": message["data"]}
        except asyncio.TimeoutError:
            yield {"data": json.dumps({"type": "timeout"})}
        finally:
            await pubsub.unsubscribe(channel)
            await redis.aclose()

    return EventSourceResponse(generator())


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[NotificationResponse]],
)
async def get_notifications(
    use_case: FromDishka[GetNotificationsUseCase],
    current_user: UserContext = Depends(get_current_user),
    unread_only: bool = Query(default=False, alias="unreadOnly"),
) -> ApiResponse[list[NotificationResponse]]:
    notifications = await use_case.execute(current_user.id, unread_only=unread_only)
    return ApiResponse.ok([NotificationResponse.from_entity(n) for n in notifications])


@router.patch(
    "/read-all",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def mark_all_as_read(
    use_case: FromDishka[MarkAllAsReadUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    await use_case.execute(current_user.id)
    return ApiResponse.ok(None)


@router.patch(
    "/{notification_id}/read",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def mark_as_read(
    notification_id: str,
    use_case: FromDishka[MarkAsReadUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    await use_case.execute(notification_id, current_user.id)
    return ApiResponse.ok(None)


@router.delete(
    "/{notification_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def delete_notification(
    notification_id: str,
    use_case: FromDishka[DeleteNotificationUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    await use_case.execute(notification_id, current_user.id)
    return ApiResponse.ok(None)


@router.delete(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[None],
)
async def delete_notifications(
    use_case: FromDishka[DeleteNotificationsUseCase],
    current_user: UserContext = Depends(get_current_user),
    read_only: bool = Query(default=False, alias="readOnly"),
) -> ApiResponse[None]:
    await use_case.execute(current_user.id, read_only=read_only)
    return ApiResponse.ok(None)
