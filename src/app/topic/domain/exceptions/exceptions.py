from app.shared.domain.exceptions.base import BaseAppException


class TopicNotFoundException(BaseAppException):
    code = "TOPIC_NOT_FOUND"


class TopicNameDuplicatedException(BaseAppException):
    code = "TOPIC_NAME_DUPLICATED"


class TopicLimitReachedException(BaseAppException):
    code = "TOPIC_LIMIT_REACHED"

    def __init__(self, limit: int) -> None:
        super().__init__(
            message=f"Topic limit reached: {limit}",
            details=[{"limit": limit}],
        )


class DigestNotFoundException(BaseAppException):
    code = "TOPIC_DIGEST_NOT_FOUND"


class DigestAlreadyInProgressException(BaseAppException):
    code = "TOPIC_DIGEST_ALREADY_IN_PROGRESS"


class DigestRateLimitExceededException(BaseAppException):
    code = "TOPIC_DIGEST_RATE_LIMIT_EXCEEDED"

    def __init__(self, limit: int, window_seconds: int, retry_after_seconds: int) -> None:
        super().__init__(
            message="주제 정리 생성 한도 초과",
            details=[{
                "limit": limit,
                "windowSeconds": window_seconds,
                "retryAfterSeconds": retry_after_seconds,
            }],
        )
