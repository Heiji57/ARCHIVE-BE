import asyncio
import json

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis
from sse_starlette.sse import EventSourceResponse

from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.infrastructure.config.settings import get_settings
from app.shared.presentation.schemas.response import ApiResponse
from app.topic.application.dtos.commands import (
    CreateTopicCommand,
    DeleteTopicCommand,
    GenerateDigestCommand,
)
from app.topic.application.dtos.queries import GetDigestByIdQuery, GetDigestQuery, GetTopicsQuery
from app.topic.application.use_cases.create_topic import CreateTopicUseCase
from app.topic.application.use_cases.delete_topic import DeleteTopicUseCase
from app.topic.application.use_cases.generate_digest import GenerateDigestUseCase
from app.topic.application.use_cases.get_digest import GetDigestUseCase
from app.topic.application.use_cases.get_topics import GetTopicsUseCase
from app.topic.domain.models.value_objects import DigestStatus
from app.topic.presentation.requests.requests import CreateTopicRequest
from app.topic.presentation.responses.responses import TopicDigestResponse, TopicResponse

router = APIRouter(prefix="/topics", tags=["topics"], route_class=DishkaRoute)

_SSE_TIMEOUT = 120  # seconds


def _to_topic_response(topic) -> TopicResponse:
    return TopicResponse(
        id=topic.id,
        name=topic.name,
        description=topic.description,
        created_at=topic.created_at,
        updated_at=topic.updated_at,
    )


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
    topics = await use_case.execute(GetTopicsQuery(user_id=current_user.id))
    return ApiResponse.ok([_to_topic_response(t) for t in topics])


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
                    if message["type"] == "message":
                        yield {"data": message["data"]}
                        break
        except asyncio.TimeoutError:
            yield {"data": json.dumps({"status": "timeout"})}
        finally:
            await pubsub.unsubscribe(channel)
            await redis.aclose()

    return EventSourceResponse(generator())
