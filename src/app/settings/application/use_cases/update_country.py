from dataclasses import dataclass
from datetime import datetime, timezone

from app.auth.domain.exceptions.exceptions import (
    CountryInvalidException,
    CountryRegionRequiredException,
)
from app.shared.domain.utils.timezone import (
    is_multi_tz_country,
    is_supported_country,
    resolve_timezone,
)
from app.user.domain.exceptions.exceptions import UserNotFoundException
from app.user.domain.models.user import User
from app.user.domain.repositories.repository import IUserRepository


@dataclass(frozen=True)
class UpdateCountryCommand:
    user_id: str
    country: str
    region: str | None = None


class UpdateCountryUseCase:
    """국가 변경 시 timezone도 자동 재계산해 같이 갱신."""

    def __init__(self, user_repo: IUserRepository) -> None:
        self._user_repo = user_repo

    async def execute(self, cmd: UpdateCountryCommand) -> User:
        user = await self._user_repo.find_by_id(cmd.user_id)
        if user is None:
            raise UserNotFoundException()

        if not is_supported_country(cmd.country):
            raise CountryInvalidException(f"Unsupported country: {cmd.country}")
        if is_multi_tz_country(cmd.country) and not cmd.region:
            raise CountryRegionRequiredException(f"Region required for {cmd.country}")
        try:
            tz = resolve_timezone(cmd.country, cmd.region)
        except ValueError as e:
            raise CountryInvalidException(str(e))

        user.country = cmd.country
        user.region = cmd.region
        user.timezone = tz
        user.updated_at = datetime.now(timezone.utc)
        return await self._user_repo.save(user)
