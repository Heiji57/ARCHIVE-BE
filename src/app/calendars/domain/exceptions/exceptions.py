from app.shared.domain.exceptions.base import BaseAppException


class CalendarNotFoundException(BaseAppException):
    code = "CALENDAR_NOT_FOUND"


class CalendarDefaultUndeletableException(BaseAppException):
    code = "CALENDAR_DEFAULT_UNDELETABLE"


class CalendarLimitExceededException(BaseAppException):
    code = "CALENDAR_LIMIT_EXCEEDED"


class CalendarNameDuplicateException(BaseAppException):
    code = "CALENDAR_NAME_DUPLICATE"
