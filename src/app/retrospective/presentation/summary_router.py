import asyncio
import json

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query, status
from sse_starlette.sse import EventSourceResponse

from app.github.domain.repositories.retrospective_push_repository import (
    IRetrospectivePushRepository,
)
from app.github.domain.utils.period_mapping import summary_to_period
from app.retrospective.application.dtos.summary_commands import RequestSummaryCommand
from app.retrospective.application.dtos.summary_queries import SummaryReadinessQuery
from app.retrospective.application.use_cases.get_summaries import GetSummariesUseCase
from app.retrospective.application.use_cases.get_summary import GetSummaryUseCase
from app.retrospective.application.use_cases.get_summary_readiness import (
    GetSummaryReadinessUseCase,
)
from app.retrospective.application.use_cases.get_summary_usage import (
    GetSummaryUsageUseCase,
)
from app.retrospective.application.use_cases.request_summary import RequestSummaryUseCase
from app.retrospective.domain.models.value_objects import SummaryStatus, SummaryType
from app.retrospective.presentation.responses.summary_responses import (
    SummaryReadinessResponse,
    SummaryResponse,
    SummaryUsageResponse,
)
from app.shared.domain.context.user_context import UserContext
from app.shared.domain.exceptions.base import BaseAppException
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.infrastructure.config.settings import get_settings
from app.shared.presentation.schemas.response import ApiResponse

router = APIRouter(prefix="/summaries", tags=["summaries"], route_class=DishkaRoute)

_VALID_SUMMARY_TYPES = {"weekly", "monthly", "annual"}
_SSE_TIMEOUT = 300  # 5분


@router.post(
    "/generate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[SummaryResponse],
)
async def generate_summary(
    use_case: FromDishka[RequestSummaryUseCase],
    current_user: UserContext = Depends(get_current_user),
    summary_type: str = Query(alias="type"),
    period_start: str | None = Query(default=None, alias="periodStart"),
    force: bool = Query(default=False),
) -> ApiResponse[SummaryResponse]:
    parsed_start = None
    if period_start:
        from datetime import date
        parsed_start = date.fromisoformat(period_start)

    summary = await use_case.execute(
        RequestSummaryCommand(
            user_id=current_user.id,
            summary_type=SummaryType(summary_type),
            period_start=parsed_start,
            force=force,
        )
    )
    return ApiResponse.accepted(SummaryResponse.from_entity(summary))


@router.get(
    "/usage",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[SummaryUsageResponse],
)
async def get_summary_usage(
    use_case: FromDishka[GetSummaryUsageUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[SummaryUsageResponse]:
    report = await use_case.execute(current_user.id)
    return ApiResponse.ok(SummaryUsageResponse.from_entity(report))


@router.get(
    "/readiness",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[SummaryReadinessResponse],
)
async def get_summary_readiness(
    use_case: FromDishka[GetSummaryReadinessUseCase],
    current_user: UserContext = Depends(get_current_user),
    summary_type: str = Query(alias="type"),
    period_start: str | None = Query(default=None, alias="periodStart"),
) -> ApiResponse[SummaryReadinessResponse]:
    parsed_start = None
    if period_start:
        from datetime import date
        parsed_start = date.fromisoformat(period_start)

    readiness = await use_case.execute(
        SummaryReadinessQuery(
            user_id=current_user.id,
            summary_type=SummaryType(summary_type),
            period_start=parsed_start,
        )
    )
    return ApiResponse.ok(SummaryReadinessResponse.from_entity(readiness))


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[SummaryResponse]],
)
async def get_summaries(
    use_case: FromDishka[GetSummariesUseCase],
    push_repo: FromDishka[IRetrospectivePushRepository],
    current_user: UserContext = Depends(get_current_user),
    summary_type: str = Query(alias="type"),
) -> ApiResponse[list[SummaryResponse]]:
    summaries = await use_case.execute(
        user_id=current_user.id,
        summary_type=SummaryType(summary_type),
    )
    keys = [summary_to_period(s) for s in summaries]
    pushes = await push_repo.find_many(current_user.id, keys)
    push_map = {(p.period_type, p.period_key): p for p in pushes}
    return ApiResponse.ok([
        SummaryResponse.from_entity(s, push_map.get(summary_to_period(s)))
        for s in summaries
    ])


@router.get(
    "/{summary_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[SummaryResponse],
)
async def get_summary(
    summary_id: str,
    use_case: FromDishka[GetSummaryUseCase],
    push_repo: FromDishka[IRetrospectivePushRepository],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[SummaryResponse]:
    summary = await use_case.execute(summary_id, current_user.id)
    period_type, period_key = summary_to_period(summary)
    push = await push_repo.find_by_period(current_user.id, period_type, period_key)
    return ApiResponse.ok(SummaryResponse.from_entity(summary, push))


@router.get("/{summary_id}/stream")
async def summary_stream(
    summary_id: str,
    use_case: FromDishka[GetSummaryUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> EventSourceResponse:
    settings = get_settings()

    async def generator():
        # 이미 완료/실패 상태면 즉시 반환
        try:
            summary = await use_case.execute(summary_id, current_user.id)
        except BaseAppException as e:
            yield {"data": json.dumps({"status": "error", "error": e.code})}
            return

        if summary.status in (SummaryStatus.COMPLETED, SummaryStatus.FAILED):
            yield {"data": json.dumps({"status": summary.status.value, "summary_id": summary_id})}
            return

        # Redis pub/sub로 Celery 태스크 완료 대기
        from redis.asyncio import Redis
        redis = Redis.from_url(settings.redis.cache_url, decode_responses=True)
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"summary:{summary_id}")

        try:
            async with asyncio.timeout(_SSE_TIMEOUT):
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        yield {"data": message["data"]}
                        break
        except asyncio.TimeoutError:
            yield {"data": json.dumps({"status": "timeout", "summary_id": summary_id})}
        finally:
            await pubsub.unsubscribe(f"summary:{summary_id}")
            await redis.aclose()

    return EventSourceResponse(generator())
