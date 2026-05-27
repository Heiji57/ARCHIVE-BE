from dataclasses import dataclass


@dataclass(frozen=True)
class UserContext:
    id: str
    email: str
