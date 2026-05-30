from enum import StrEnum


class NotificationType(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class NotificationCategory(StrEnum):
    SYNC = "sync"
    SUMMARY = "summary"
    SYSTEM = "system"
