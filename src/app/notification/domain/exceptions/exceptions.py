from app.shared.domain.exceptions.base import BaseAppException


class NotificationNotFoundException(BaseAppException):
    code = "NOTIFICATION_NOT_FOUND"
