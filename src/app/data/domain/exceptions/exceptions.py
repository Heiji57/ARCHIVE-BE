from app.shared.domain.exceptions.base import BaseAppException


class TrashItemNotFoundException(BaseAppException):
    """휴지통에 그 항목이 없음(이미 되살렸거나 영구 삭제됨, 또는 다른 사용자 것)."""

    code = "TRASH_ITEM_NOT_FOUND"


class TrashKindInvalidException(BaseAppException):
    """kind 는 todo 또는 entry."""

    code = "TRASH_KIND_INVALID"


class ExportInProgressException(BaseAppException):
    """이미 만들고 있는 내보내기가 있음(사용자당 동시에 하나)."""

    code = "EXPORT_IN_PROGRESS"


class ExportDailyLimitException(BaseAppException):
    """최근 24시간 내보내기 3번 초과."""

    code = "EXPORT_DAILY_LIMIT"


class ExportNotFoundException(BaseAppException):
    code = "EXPORT_NOT_FOUND"


class ExportExpiredException(BaseAppException):
    """파일 보관 기간(7일)이 지나 지워짐."""

    code = "EXPORT_EXPIRED"
