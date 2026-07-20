from app.shared.domain.exceptions.base import BaseAppException


class UserNotFoundException(BaseAppException):
    code = "USER_NOT_FOUND"


class UserEmailDuplicatedException(BaseAppException):
    code = "USER_EMAIL_DUPLICATED"


class InvalidEmailException(BaseAppException):
    code = "USER_EMAIL_INVALID"
