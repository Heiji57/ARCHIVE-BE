from enum import StrEnum


class TaskStatus(StrEnum):
    NOT_START = "not-start"
    IN_PROGRESS = "in-progress"
    DONE = "done"
