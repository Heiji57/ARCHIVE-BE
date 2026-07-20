from dataclasses import dataclass
from datetime import datetime, timezone

from app.user.domain.exceptions.exceptions import UserNotFoundException
from app.user.domain.models.user import User
from app.user.domain.repositories.repository import IUserRepository


@dataclass(frozen=True)
class UpdateProfileCommand:
    user_id: str
    display_name: str | None = None
    account_type: str | None = None


class UpdateProfileUseCase:
    def __init__(self, user_repo: IUserRepository) -> None:
        self._user_repo = user_repo

    async def execute(self, cmd: UpdateProfileCommand) -> User:
        from dataclasses import replace

        user = await self._user_repo.find_by_id(cmd.user_id)
        if not user:
            raise UserNotFoundException()

        updates: dict = {"updated_at": datetime.now(timezone.utc)}
        if cmd.account_type is not None:
            updates["account_type"] = cmd.account_type

        updated = replace(user, **updates)
        return await self._user_repo.save(updated)
