from app.shared.domain.exceptions.base import BaseAppException


class JournalEntryNotFoundException(BaseAppException):
    code = "JOURNAL_ENTRY_NOT_FOUND"


class JournalEntryAlreadyExistsException(BaseAppException):
    code = "JOURNAL_ENTRY_ALREADY_EXISTS"


class RetroSummaryNotFoundException(BaseAppException):
    code = "RETRO_SUMMARY_NOT_FOUND"


class SummaryAlreadyInProgressException(BaseAppException):
    code = "RETRO_SUMMARY_ALREADY_IN_PROGRESS"


class SummaryInvalidStateException(BaseAppException):
    code = "RETRO_SUMMARY_INVALID_STATE"


class SummaryReadinessUnsupportedException(BaseAppException):
    code = "RETRO_SUMMARY_READINESS_UNSUPPORTED"


class SummaryTemplateNotFoundException(BaseAppException):
    code = "RETRO_SUMMARY_TEMPLATE_NOT_FOUND"


class SummaryTemplateNameDuplicatedException(BaseAppException):
    code = "RETRO_SUMMARY_TEMPLATE_NAME_DUPLICATED"


class SummaryTemplateLimitReachedException(BaseAppException):
    code = "RETRO_SUMMARY_TEMPLATE_LIMIT_REACHED"

    def __init__(
        self, summary_type: str, limit: int
    ) -> None:
        super().__init__(
            message=f"Per-type template limit ({limit}) reached for {summary_type}.",
            details=[{"summaryType": summary_type, "limit": limit}],
        )


class SummaryTemplateInUseException(BaseAppException):
    """현재 활성으로 지정된 템플릿은 삭제할 수 없다."""
    code = "RETRO_SUMMARY_TEMPLATE_IN_USE"


class SummaryRateLimitExceededException(BaseAppException):
    code = "RETRO_SUMMARY_RATE_LIMIT_EXCEEDED"

    def __init__(
        self,
        summary_type: str,
        limit: int,
        window_seconds: int,
        retry_after_seconds: int,
    ) -> None:
        super().__init__(
            message="AI 요약 생성 한도 초과",
            details=[{
                "summaryType": summary_type,
                "limit": limit,
                "windowSeconds": window_seconds,
                "retryAfterSeconds": retry_after_seconds,
            }],
        )
