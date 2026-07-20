from app.shared.domain.exceptions.base import BaseAppException


class TodoNotFoundException(BaseAppException):
    code = "TODO_NOT_FOUND"


class TodoAlreadyCompletedException(BaseAppException):
    code = "TODO_ALREADY_COMPLETED"


class TodoAlreadyInProgressException(BaseAppException):
    code = "TODO_ALREADY_IN_PROGRESS"
