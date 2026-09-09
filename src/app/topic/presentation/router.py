import asyncio
import json

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query, status
from redis.asyncio import Redis
from sse_starlette.sse import EventSourceResponse

from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.infrastructure.config.settings import get_settings
from app.shared.presentation.schemas.response import ApiResponse
from app.todo.presentation.responses.responses import TagCountResponse
from app.topic.application.dtos.commands import (
    CreateTopicCommand,
    DeleteTopicCommand,
    GenerateDigestCommand,
    UpdateTopicCommand,
)
from app.topic.application.dtos.queries import (
    GetDigestByIdQuery,
    GetDigestQuery,
    GetTopicSourcesQuery,
    GetTopicStatsQuery,
    GetTopicsQuery,
)
from app.topic.application.use_cases.create_topic import CreateTopicUseCase
from app.topic.application.use_cases.delete_topic import DeleteTopicUseCase
from app.topic.application.use_cases.generate_digest import GenerateDigestUseCase
from app.topic.application.use_cases.get_digest import GetDigestUseCase
from app.topic.application.use_cases.get_topic_sources import GetTopicSourcesUseCase
from app.topic.application.use_cases.get_topic_stats import GetTopicStatsUseCase
from app.topic.application.use_cases.get_topics import GetTopicsUseCase
from app.topic.application.use_cases.update_topic import UpdateTopicUseCase
from app.topic.domain.models.value_objects import DigestStatus
from app.topic.presentation.requests.requests import CreateTopicRequest, UpdateTopicRequest
from app.topic.presentation.responses.responses import (
    EntryCountsResponse,
    TodoCountsResponse,
    TopicDigestResponse,
    TopicResponse,
    TopicSourcePageResponse,
    TopicSourceResponse,
    TopicStatsResponse,
)

router = APIRouter(prefix="/topics", tags=["topics"], route_class=DishkaRoute)

_SSE_TIMEOUT = 120  # seconds
_TERMINAL_STATUSES = {DigestStatus.COMPLETED.value, DigestStatus.FAILED.value}


def _is_terminal(payload: str) -> bool:
    """워커가 보낸 이벤트가 종료 상태인지. 파싱 실패 시 스트림을 닫아 매달리지 않게 한다."""
    try:
        return json.loads(payload).get("status") in _TERMINAL_STATUSES
    except (json.JSONDecodeError, AttributeError):
        return True


def _to_topic_response(topic) -> TopicResponse:
    return TopicResponse(
        id=topic.id,
        name=topic.name,
        description=topic.description,
        created_at=topic.created_at,
        updated_at=topic.updated_at,
    )


def _to_topic_summary_response(summary) -> TopicResponse:
    response = _to_topic_response(summary.topic)
    response.entry_count = summary.entry_count
    response.todo_count = summary.todo_count
    response.digest_watermark_date_key = summary.digest_watermark_date_key
    return response


def _to_digest_response(digest) -> TopicDigestResponse:
    return TopicDigestResponse(
        id=digest.id,
        topic_id=digest.topic_id,
        status=digest.status,
        content=digest.content,
        watermark_date_key=digest.watermark_date_key,
        created_at=digest.created_at,
        updated_at=digest.updated_at,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_topic(
    body: CreateTopicRequest,
    use_case: FromDishka[CreateTopicUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[TopicResponse]:
    topic = await use_case.execute(
        CreateTopicCommand(
            user_id=current_user.id,
            name=body.name,
            description=body.description,
        )
    )
    return ApiResponse.created(_to_topic_response(topic))


@router.get("")
async def get_topics(
    use_case: FromDishka[GetTopicsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[list[TopicResponse]]:
    summaries = await use_case.execute(GetTopicsQuery(user_id=current_user.id))
    return ApiResponse.ok([_to_topic_summary_response(s) for s in summaries])


@router.patch("/{topic_id}")
async def update_topic(
    topic_id: str,
    body: UpdateTopicRequest,
    use_case: FromDishka[UpdateTopicUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[TopicResponse]:
    topic = await use_case.execute(
        UpdateTopicCommand(
            user_id=current_user.id,
            topic_id=topic_id,
            name=body.name,
            description=body.description,
        )
    )
    return ApiResponse.ok(_to_topic_response(topic))


@router.get("/{topic_id}/stats")
async def get_topic_stats(
    topic_id: str,
    use_case: FromDishka[GetTopicStatsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[TopicStatsResponse]:
    stats = await use_case.execute(
        GetTopicStatsQuery(user_id=current_user.id, topic_id=topic_id)
    )
    return ApiResponse.ok(
        TopicStatsResponse(
            topic_id=stats.topic_id,
            entry_counts=EntryCountsResponse(
                daily=stats.entry_counts.daily,
                weekly=stats.entry_counts.weekly,
                monthly=stats.entry_counts.monthly,
                yearly=stats.entry_counts.yearly,
                total=stats.entry_counts.total,
            ),
            todo_counts=TodoCountsResponse(
                total=stats.todo_counts.total,
                completed=stats.todo_counts.completed,
            ),
            tag_counts=[TagCountResponse.from_domain(t) for t in stats.tag_counts],
            tag_count_total=stats.tag_count_total,
            period_start_date_key=stats.period_start_date_key,
            period_end_date_key=stats.period_end_date_key,
            unreflected_entry_count=stats.unreflected_entry_count,
        )
    )


@router.get("/{topic_id}/sources")
async def get_topic_sources(
    topic_id: str,
    use_case: FromDishka[GetTopicSourcesUseCase],
    current_user: UserContext = Depends(get_current_user),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[TopicSourcePageResponse]:
    result = await use_case.execute(
        GetTopicSourcesQuery(
            user_id=current_user.id, topic_id=topic_id, page=page, size=size
        )
    )
    return ApiResponse.ok(
        TopicSourcePageResponse(
            items=[
                TopicSourceResponse(
                    kind=s.kind,
                    id=s.id,
                    title=s.title,
                    date_key=s.date_key,
                    retro_type=s.retro_type,
                )
                for s in result.items
            ],
            total=result.total,
            page=result.page,
            size=result.size,
            digest_watermark_date_key=result.digest_watermark_date_key,
        )
    )


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(
    topic_id: str,
    use_case: FromDishka[DeleteTopicUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> None:
    await use_case.execute(DeleteTopicCommand(user_id=current_user.id, topic_id=topic_id))


@router.post("/{topic_id}/digest/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_digest(
    topic_id: str,
    use_case: FromDishka[GenerateDigestUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[TopicDigestResponse]:
    digest = await use_case.execute(
        GenerateDigestCommand(user_id=current_user.id, topic_id=topic_id)
    )
    # Enqueue Celery task
    from app.worker.tasks.generate_digest import generate_digest_task
    generate_digest_task.apply_async(
        args=[digest.id, topic_id, current_user.id],
        queue="ai_tasks",
    )
    return ApiResponse.accepted(_to_digest_response(digest))


@router.get("/{topic_id}/digest")
async def get_digest(
    topic_id: str,
    use_case: FromDishka[GetDigestUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[TopicDigestResponse]:
    digest = await use_case.execute(GetDigestQuery(user_id=current_user.id, topic_id=topic_id))
    return ApiResponse.ok(_to_digest_response(digest))


@router.get("/{topic_id}/digest/stream")
async def stream_digest(
    topic_id: str,
    use_case: FromDishka[GetDigestUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> EventSourceResponse:
    digest = await use_case.execute(GetDigestQuery(user_id=current_user.id, topic_id=topic_id))
    digest_id = digest.id

    async def generator():
        if digest.status in (DigestStatus.COMPLETED, DigestStatus.FAILED):
            yield {"data": json.dumps({"status": digest.status.value})}
            return

        settings = get_settings()
        redis = Redis.from_url(settings.redis.cache_url, decode_responses=True)
        pubsub = redis.pubsub()
        channel = f"topic:digest:{digest_id}"
        await pubsub.subscribe(channel)
        try:
            async with asyncio.timeout(_SSE_TIMEOUT):
                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    yield {"data": message["data"]}
                    # in_progress 진행률 이벤트는 계속 흘리고, terminal 상태에서만 닫는다.
                    if _is_terminal(message["data"]):
                        break
        except asyncio.TimeoutError:
            yield {"data": json.dumps({"status": "timeout"})}
        finally:
            await pubsub.unsubscribe(channel)
            await redis.aclose()

    return EventSourceResponse(generator())
