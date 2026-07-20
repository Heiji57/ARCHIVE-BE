from dataclasses import dataclass
from datetime import datetime, timezone

from app.auth.domain.exceptions.exceptions import (
    CountryInvalidException,
    CountryTimezoneRequiredException,
)
from app.shared.domain.utils.timezone import (
    is_multi_tz_country,
    is_supported_country,
    resolve_timezone,
)
from app.user.domain.exceptions.exceptions import UserNotFoundException
from app.user.domain.models.user import User
from app.user.domain.repositories.country_history_repository import (
    CountryChangeSource,
    ICountryHistoryRepository,
)
from app.user.domain.repositories.repository import IUserRepository


@dataclass(frozen=True)
class UpdateCountryCommand:
    user_id: str
    country: str
    timezone: str | None = None    # 다중 tz 국가일 때 필수


class UpdateCountryUseCase:
    """국가 변경 시 timezone 도 함께 결정해 저장.

    단일 tz 국가 (예: KR, JP) 는 timezone 생략 가능 — 자동 결정.
    다중 tz 국가 (예: US, RU, BR) 는 IANA timezone 명시 필수.

    실제로 변경된 경우(이전 값과 다른 경우)에만 history 기록.
    """

    def __init__(
        self,
        user_repo: IUserRepository,
        country_history_repo: ICountryHistoryRepository,
    ) -> None:
        self._user_repo = user_repo
        self._country_history_repo = country_history_repo

    async def execute(self, cmd: UpdateCountryCommand) -> User:
        user = await self._user_repo.find_by_id(cmd.user_id)
        if user is None:
            raise UserNotFoundException()

        if not is_supported_country(cmd.country):
            raise CountryInvalidException(f"Unsupported country: {cmd.country}")
        if is_multi_tz_country(cmd.country) and not cmd.timezone:
            raise CountryTimezoneRequiredException(
                f"Timezone required for multi-timezone country: {cmd.country}"
            )
        try:
            tz = resolve_timezone(cmd.country, cmd.timezone)
        except ValueError as e:
            raise CountryInvalidException(str(e))

        changed = user.country != cmd.country or user.timezone != tz

        now = datetime.now(timezone.utc)
        user.country = cmd.country
        user.region = None          # 신 정책: region 입력 받지 않음. 기존 값 비움.
        user.timezone = tz
        user.updated_at = now
        saved = await self._user_repo.save(user)

        if changed:
            await self._country_history_repo.record(
                user_id=saved.id,
                country=cmd.country,
                region=None,
                timezone=tz,
                source=CountryChangeSource.SETTINGS_UPDATE,
                at=now,
            )
        return saved
