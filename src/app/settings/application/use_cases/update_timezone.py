from dataclasses import dataclass
from datetime import datetime, timezone

from app.auth.domain.exceptions.exceptions import TimezoneInvalidException
from app.shared.domain.utils.timezone import validate_timezone
from app.user.domain.exceptions.exceptions import UserNotFoundException
from app.user.domain.models.user import User
from app.user.domain.repositories.repository import IUserRepository


@dataclass(frozen=True)
class UpdateTimezoneCommand:
    user_id: str
    timezone: str


class UpdateTimezoneUseCase:
    """국가와 무관한 tz 단독 override. country는 유지된다."""

    def __init__(self, user_repo: IUserRepository) -> None:
        self._user_repo = user_repo

    async def execute(self, cmd: UpdateTimezoneCommand) -> User:
        user = await self._user_repo.find_by_id(cmd.user_id)
        if user is None:
            raise UserNotFoundException()

        if not validate_timezone(cmd.timezone):
            raise TimezoneInvalidException(f"Invalid IANA timezone: {cmd.timezone}")

        user.timezone = cmd.timezone
        user.updated_at = datetime.now(timezone.utc)
        return await self._user_repo.save(user)
