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
