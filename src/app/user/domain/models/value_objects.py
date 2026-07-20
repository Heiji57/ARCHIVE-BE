import re
from dataclasses import dataclass

from app.user.domain.exceptions.exceptions import InvalidEmailException

_EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        if not _EMAIL_REGEX.match(self.value):
            raise InvalidEmailException(f"Invalid email format: {self.value}")

    def __str__(self) -> str:
        return self.value
