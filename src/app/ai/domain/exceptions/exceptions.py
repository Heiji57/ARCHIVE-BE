from app.shared.domain.exceptions.base import BaseAppException


class AiSuggestionNotFoundException(BaseAppException):
    code = "AI_SUGGESTION_NOT_FOUND"


class AiSuggestionActionInvalidException(BaseAppException):
    """없는 행동 번호이거나, 지금 상태에서 할 수 없는 동작(이미 적용됨·넘김 등)."""

    code = "AI_SUGGESTION_ACTION_INVALID"


class AiUsageLimitExceededException(BaseAppException):
    """사용자별 하루·한 달 AI 요청 상한 초과. details[0] 에 {scope, used, limit}."""

    code = "AI_USAGE_LIMIT_EXCEEDED"


class AiConversationNotFoundException(BaseAppException):
    code = "AI_CONVERSATION_NOT_FOUND"


class AiProposalNotFoundException(BaseAppException):
    code = "AI_PROPOSAL_NOT_FOUND"


class AiProposalAlreadyAppliedException(BaseAppException):
    code = "AI_PROPOSAL_ALREADY_APPLIED"


class AiProposalStaleException(BaseAppException):
    """적용 전에 대상 할 일이 바뀜 — 제안이 본 값과 지금 값이 다르다. details 에 [{key, todoId}]."""

    code = "AI_PROPOSAL_STALE"


class AiProposalStateInvalidException(BaseAppException):
    """지금 상태에서 할 수 없는 동작(적용 안 한 제안 되돌리기, 넘긴 제안 적용 등)."""

    code = "AI_PROPOSAL_STATE_INVALID"


class AiProposalItemsInvalidException(BaseAppException):
    """적용할 항목 key 가 제안에 없거나, 고른 항목이 없음."""

    code = "AI_PROPOSAL_ITEMS_INVALID"


class AiToolDisabledException(BaseAppException):
    """설정에서 끈 출처(캘린더·할 일·회고·GitHub)의 도구."""

    code = "AI_TOOL_DISABLED"


class AiLlmUnavailableException(BaseAppException):
    code = "AI_LLM_UNAVAILABLE"


class AiMemoryLimitExceededException(BaseAppException):
    """알려 둔 것은 50개까지."""

    code = "AI_MEMORY_LIMIT_EXCEEDED"


class AiMemoryNotFoundException(BaseAppException):
    code = "AI_MEMORY_NOT_FOUND"


class AiScheduleLimitExceededException(BaseAppException):
    """예약한 일은 20개까지."""

    code = "AI_SCHEDULE_LIMIT_EXCEEDED"


class AiScheduleNotFoundException(BaseAppException):
    code = "AI_SCHEDULE_NOT_FOUND"
