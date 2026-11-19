from enum import StrEnum


class NotificationType(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class NotificationCategory(StrEnum):
    SYNC = "sync"
    SUMMARY = "summary"
    SYSTEM = "system"  # 끌 수 없다
    DUE = "due"  # 마감 알림(오늘 마감, 지난 마감)
    SCHEDULE = "schedule"  # 하루 마무리 알림, AI 예약한 일의 결과
    AI = "ai"  # AI 작업 완료, 제안 도착
