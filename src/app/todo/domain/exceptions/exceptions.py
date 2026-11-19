from app.shared.domain.exceptions.base import BaseAppException


class TodoNotFoundException(BaseAppException):
    code = "TODO_NOT_FOUND"


class TodoAlreadyCompletedException(BaseAppException):
    code = "TODO_ALREADY_COMPLETED"


class TodoAlreadyInProgressException(BaseAppException):
    code = "TODO_ALREADY_IN_PROGRESS"


class TodoBatchFailedException(BaseAppException):
    """묶음 수정 중 하나 이상 실패 — 전체 롤백. details 에 `[{id, code}]`."""

    code = "TODO_BATCH_FAILED"


class TodoQueryConflictException(BaseAppException):
    """GET /todos 조회 모드(dateKey·from/to, overdue, due, calendarPushStatus)를 섞어 보냄."""

    code = "TODO_QUERY_CONFLICT"


class TagNotFoundException(BaseAppException):
    """사용 중인 할 일도, 색·순서 정보도 없는 태그."""

    code = "TAG_NOT_FOUND"
