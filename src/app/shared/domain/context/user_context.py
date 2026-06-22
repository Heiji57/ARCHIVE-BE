from dataclasses import dataclass, field


@dataclass(frozen=True)
class UserContext:
    id: str
    email: str
    account_type: str = field(default="user")  # "developer" | "user"

    def is_developer(self) -> bool:
        return self.account_type == "developer"
