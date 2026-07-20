from enum import StrEnum


class TaskStatus(StrEnum):
    NOT_START = "not-start"
    IN_PROGRESS = "in-progress"
    DONE = "done"
    # 반복 시리즈 인스턴스 취소 전용 — 사용자가 API 로 직접 지정 불가.
    # "이번만 삭제" 시 해당 슬롯 exception row 의 status 로만 사용된다.
    CANCELLED = "cancelled"
