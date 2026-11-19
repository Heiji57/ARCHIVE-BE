"""AI 비서 — 추천(5a), 대화와 제안(5b). AI 는 제안만 하고, 사용자가 누를 때만 데이터를 바꾼다."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import date

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from redis.asyncio import Redis
from sse_starlette.sse import EventSourceResponse

from app.ai.application.use_cases.ai_settings import AiSettingsUseCase
from app.ai.application.use_cases.conversations import ConversationsUseCase, PostMessageUseCase
from app.ai.application.use_cases.proposals import ProposalsUseCase
from app.ai.application.use_cases.suggestions import (
    ApplySuggestionUseCase,
    DismissSuggestionUseCase,
    GetSuggestionsUseCase,
    UndoSuggestionUseCase,
)
from app.ai.application.use_cases.usage import GetAiUsageUseCase
from app.ai.infrastructure.events import CHANNEL
from app.ai.presentation.requests.requests import (
    AddMemoryRequest,
    ApplyProposalRequest,
    ApplySuggestionRequest,
    CreateConversationRequest,
    CreateScheduleRequest,
    PatchAiSettingsRequest,
    PostMessageRequest,
    UpdateScheduleRequest,
)
from app.ai.presentation.responses.responses import (
    AiSettingsResponse,
    AiUsageResponse,
    ApplySuggestionResponse,
    ConversationResponse,
    MemoryResponse,
    MessageResponse,
    ProposalResponse,
    ScheduleResponse,
    SuggestionResponse,
    UndoProposalResponse,
)
from app.shared.domain.context.user_context import UserContext
from app.shared.infrastructure.auth.jwt import get_current_user
from app.shared.infrastructure.config.settings import get_settings
from app.shared.presentation.schemas.response import ApiResponse

router = APIRouter(prefix="/ai", tags=["ai"], route_class=DishkaRoute)


@router.get("/suggestions", response_model=ApiResponse[list[SuggestionResponse]])
async def get_suggestions(
    use_case: FromDishka[GetSuggestionsUseCase],
    current_user: UserContext = Depends(get_current_user),
    day: date = Query(alias="date"),
) -> ApiResponse[list[SuggestionResponse]]:
    """그날의 추천(지난 마감·빈 칸·커밋과 맞는 일). 넘긴 추천은 다시 나오지 않는다."""
    suggestions = await use_case.execute(current_user.id, day)
    return ApiResponse.ok([SuggestionResponse.from_entity(s) for s in suggestions])


@router.post(
    "/suggestions/{suggestion_id}/apply", response_model=ApiResponse[ApplySuggestionResponse]
)
async def apply_suggestion(
    suggestion_id: str,
    body: ApplySuggestionRequest,
    use_case: FromDishka[ApplySuggestionUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[ApplySuggestionResponse]:
    s = await use_case.execute(current_user.id, suggestion_id, body.action_index)
    return ApiResponse.ok(
        ApplySuggestionResponse(
            suggestion=SuggestionResponse.from_entity(s),
            todo_id=(s.applied or {}).get("todo_id", s.todo_id),
            undo_token=s.id,
        )
    )


@router.post("/suggestions/{suggestion_id}/undo", response_model=ApiResponse[SuggestionResponse])
async def undo_suggestion(
    suggestion_id: str,
    use_case: FromDishka[UndoSuggestionUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[SuggestionResponse]:
    s = await use_case.execute(current_user.id, suggestion_id)
    return ApiResponse.ok(SuggestionResponse.from_entity(s))


@router.post("/suggestions/{suggestion_id}/dismiss", response_model=ApiResponse[SuggestionResponse])
async def dismiss_suggestion(
    suggestion_id: str,
    use_case: FromDishka[DismissSuggestionUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[SuggestionResponse]:
    s = await use_case.execute(current_user.id, suggestion_id)
    return ApiResponse.ok(SuggestionResponse.from_entity(s))


@router.get("/usage", response_model=ApiResponse[AiUsageResponse])
async def get_usage(
    use_case: FromDishka[GetAiUsageUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[AiUsageResponse]:
    """하루·한 달 AI 요청 사용량(사용자 tz). 규칙 기반 추천은 세지 않는다."""
    return ApiResponse.ok(AiUsageResponse.from_report(await use_case.execute(current_user.id)))


# ── 대화 (5b) ───────────────────────────────────────────────────────────────

_SSE_TIMEOUT = 420  # 한 차례 최악(모델 6번 × 60초 타임아웃)보다 길게
_TERMINAL = {"done", "error"}


@router.post(
    "/conversations",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[ConversationResponse],
)
async def create_conversation(
    body: CreateConversationRequest,
    use_case: FromDishka[ConversationsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[ConversationResponse]:
    c = await use_case.create(current_user.id, body.title)
    return ApiResponse.created(ConversationResponse.from_entity(c))


@router.get("/conversations", response_model=ApiResponse[list[ConversationResponse]])
async def list_conversations(
    use_case: FromDishka[ConversationsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[list[ConversationResponse]]:
    return ApiResponse.ok(
        [ConversationResponse.from_entity(c) for c in await use_case.list_all(current_user.id)]
    )


@router.delete("/conversations/{conversation_id}", response_model=ApiResponse[None])
async def delete_conversation(
    conversation_id: str,
    use_case: FromDishka[ConversationsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    await use_case.delete(current_user.id, conversation_id)
    return ApiResponse.ok(None)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=ApiResponse[list[MessageResponse]],
)
async def list_messages(
    conversation_id: str,
    use_case: FromDishka[ConversationsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[list[MessageResponse]]:
    messages = await use_case.messages(current_user.id, conversation_id)
    return ApiResponse.ok([MessageResponse.from_entity(m) for m in messages])


@router.post(
    "/conversations/{conversation_id}/messages",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[MessageResponse],
)
async def post_message(
    conversation_id: str,
    body: PostMessageRequest,
    background_tasks: BackgroundTasks,
    use_case: FromDishka[PostMessageUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[MessageResponse]:
    """사용자 메시지를 저장하고 한 차례를 워커에 맡긴다(202). 진행은 `.../stream` SSE 로."""
    message = await use_case.execute(current_user.id, conversation_id, body.text, body.context)
    from app.worker.tasks.run_ai_turn import run_ai_turn_task

    # 요약과 같은 방식 — 응답 마지막에 enqueue. 그래도 커밋보다 먼저 돌 수 있어 워커가
    # 메시지가 보일 때까지 잠시 기다렸다 다시 시도한다(MessageNotYetVisibleError).
    background_tasks.add_task(
        run_ai_turn_task.apply_async,
        args=[conversation_id, current_user.id, message.id],
        queue="ai_tasks",
    )
    return ApiResponse.accepted(MessageResponse.from_entity(message))


@router.get("/conversations/{conversation_id}/stream")
async def stream_conversation(
    conversation_id: str,
    use_case: FromDishka[ConversationsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> EventSourceResponse:
    """한 차례의 진행 — `step`(진행 문장) · `delta`(답 글자) · `proposal` · `done` · `error`.

    먼저 구독한 뒤 상태를 본다: 마지막 메시지가 이미 답(assistant)이면 차례가 끝난 것이라
    `done` 을 한 번 보내고 닫는다(구독 전에 끝난 차례를 놓치지 않게).
    """
    await use_case.messages(current_user.id, conversation_id)  # 소유 확인(404)

    async def generator() -> AsyncIterator[dict[str, str]]:
        redis = Redis.from_url(get_settings().redis.cache_url, decode_responses=True)
        pubsub = redis.pubsub()
        channel = CHANNEL.format(conversation_id=conversation_id)
        await pubsub.subscribe(channel)
        try:
            messages = await use_case.messages(current_user.id, conversation_id)
            if messages and messages[-1].role == "assistant":
                last = messages[-1]
                error = (last.context or {}).get("error")
                event = (
                    {"type": "error", "code": error}
                    if error
                    else {"type": "done", "messageId": last.id}
                )
                yield {"data": json.dumps(event)}
                return
            async with asyncio.timeout(_SSE_TIMEOUT):
                async for msg in pubsub.listen():
                    if msg["type"] != "message":
                        continue
                    yield {"data": msg["data"]}
                    try:
                        if json.loads(msg["data"]).get("type") in _TERMINAL:
                            return
                    except (json.JSONDecodeError, AttributeError):
                        return
        except TimeoutError:
            yield {"data": json.dumps({"type": "error", "code": "TIMEOUT"})}
        finally:
            await pubsub.unsubscribe(channel)
            await redis.aclose()

    return EventSourceResponse(generator())


# ── 제안 (5b) ───────────────────────────────────────────────────────────────


@router.get(
    "/conversations/{conversation_id}/proposals",
    response_model=ApiResponse[list[ProposalResponse]],
)
async def list_conversation_proposals(
    conversation_id: str,
    conversations: FromDishka[ConversationsUseCase],
    use_case: FromDishka[ProposalsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[list[ProposalResponse]]:
    """대화에서 나온 제안(만든 순) — 다시 열었을 때·SSE 를 놓쳤을 때 카드를 되살린다."""
    await conversations.messages(current_user.id, conversation_id)  # 소유 확인(404)
    proposals = await use_case.list_by_conversation(conversation_id)
    return ApiResponse.ok([ProposalResponse.from_entity(p) for p in proposals])


@router.get("/proposals/{proposal_id}", response_model=ApiResponse[ProposalResponse])
async def get_proposal(
    proposal_id: str,
    use_case: FromDishka[ProposalsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[ProposalResponse]:
    return ApiResponse.ok(
        ProposalResponse.from_entity(await use_case.get(current_user.id, proposal_id))
    )


@router.post("/proposals/{proposal_id}/apply", response_model=ApiResponse[ProposalResponse])
async def apply_proposal(
    proposal_id: str,
    use_case: FromDishka[ProposalsUseCase],
    current_user: UserContext = Depends(get_current_user),
    body: ApplyProposalRequest | None = None,
) -> ApiResponse[ProposalResponse]:
    """고른 항목만 적용(한 트랜잭션). 본문 생략 = 전부. 응답 `applied` 에 만들어지거나 바뀐 id."""
    p = await use_case.apply(current_user.id, proposal_id, body.item_keys if body else None)
    return ApiResponse.ok(ProposalResponse.from_entity(p))


@router.post("/proposals/{proposal_id}/undo", response_model=ApiResponse[UndoProposalResponse])
async def undo_proposal(
    proposal_id: str,
    use_case: FromDishka[ProposalsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[UndoProposalResponse]:
    result = await use_case.undo(current_user.id, proposal_id)
    return ApiResponse.ok(
        UndoProposalResponse(
            proposal=ProposalResponse.from_entity(result.proposal), skipped=result.skipped
        )
    )


@router.post("/proposals/{proposal_id}/dismiss", response_model=ApiResponse[ProposalResponse])
async def dismiss_proposal(
    proposal_id: str,
    use_case: FromDishka[ProposalsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[ProposalResponse]:
    return ApiResponse.ok(
        ProposalResponse.from_entity(await use_case.dismiss(current_user.id, proposal_id))
    )


# ── 설정·기억·예약 (5c) ─────────────────────────────────────────────────────


@router.get("/settings", response_model=ApiResponse[AiSettingsResponse])
async def get_ai_settings(
    use_case: FromDishka[AiSettingsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[AiSettingsResponse]:
    return ApiResponse.ok(AiSettingsResponse.from_entity(await use_case.get(current_user.id)))


@router.patch("/settings", response_model=ApiResponse[AiSettingsResponse])
async def patch_ai_settings(
    body: PatchAiSettingsRequest,
    use_case: FromDishka[AiSettingsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[AiSettingsResponse]:
    """보낸 필드만. `confirmMode` 는 1차에 `always` 고정이라 받지 않는다."""
    s = await use_case.patch(current_user.id, body.provided())
    return ApiResponse.ok(AiSettingsResponse.from_entity(s))


@router.get("/memories", response_model=ApiResponse[list[MemoryResponse]])
async def list_memories(
    use_case: FromDishka[AiSettingsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[list[MemoryResponse]]:
    return ApiResponse.ok(
        [MemoryResponse.from_entity(m) for m in await use_case.memories(current_user.id)]
    )


@router.post(
    "/memories", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[MemoryResponse]
)
async def add_memory(
    body: AddMemoryRequest,
    use_case: FromDishka[AiSettingsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[MemoryResponse]:
    m = await use_case.add_memory(current_user.id, body.text.strip())
    return ApiResponse.created(MemoryResponse.from_entity(m))


@router.delete("/memories/{memory_id}", response_model=ApiResponse[None])
async def delete_memory(
    memory_id: str,
    use_case: FromDishka[AiSettingsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    await use_case.delete_memory(current_user.id, memory_id)
    return ApiResponse.ok(None)


@router.get("/schedules", response_model=ApiResponse[list[ScheduleResponse]])
async def list_schedules(
    use_case: FromDishka[AiSettingsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[list[ScheduleResponse]]:
    return ApiResponse.ok(
        [ScheduleResponse.from_entity(s) for s in await use_case.schedules(current_user.id)]
    )


@router.post(
    "/schedules", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[ScheduleResponse]
)
async def create_schedule(
    body: CreateScheduleRequest,
    use_case: FromDishka[AiSettingsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[ScheduleResponse]:
    s = await use_case.create_schedule(
        current_user.id,
        body.prompt.strip(),
        body.repeat.model_dump(exclude_none=True),
        body.enabled,
    )
    return ApiResponse.created(ScheduleResponse.from_entity(s))


@router.patch("/schedules/{schedule_id}", response_model=ApiResponse[ScheduleResponse])
async def update_schedule(
    schedule_id: str,
    body: UpdateScheduleRequest,
    use_case: FromDishka[AiSettingsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[ScheduleResponse]:
    s = await use_case.update_schedule(current_user.id, schedule_id, body.provided())
    return ApiResponse.ok(ScheduleResponse.from_entity(s))


@router.delete("/schedules/{schedule_id}", response_model=ApiResponse[None])
async def delete_schedule(
    schedule_id: str,
    use_case: FromDishka[AiSettingsUseCase],
    current_user: UserContext = Depends(get_current_user),
) -> ApiResponse[None]:
    await use_case.delete_schedule(current_user.id, schedule_id)
    return ApiResponse.ok(None)
