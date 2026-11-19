from dataclasses import dataclass, replace
from datetime import UTC, datetime

from app.calendars.domain.exceptions.exceptions import (
    CalendarDefaultUndeletableException,
    CalendarLimitExceededException,
    CalendarNameDuplicateException,
    CalendarNotFoundException,
)
from app.calendars.domain.models.calendar import (
    DEFAULT_CALENDAR_NAME,
    MAX_CALENDARS,
    Calendar,
)
from app.calendars.domain.repositories.repository import ICalendarRepository
from app.shared.domain.utils.id import generate_id
from app.shared.domain.utils.unset import UNSET, _Unset


async def ensure_default(repo: ICalendarRepository, user_id: str) -> Calendar:
    """기본 캘린더를 돌려준다. 없으면 만든다(가입 시점과 무관하게 항상 하나 있게)."""
    default = await repo.find_default(user_id)
    if default is not None:
        return default
    return await repo.ensure_default(
        user_id,
        Calendar(
            id=generate_id("cal"),  # 저장소가 결정적 id 로 바꾼다
            user_id=user_id,
            name=DEFAULT_CALENDAR_NAME,
            is_default=True,
            push_to_google=True,
            created_at=datetime.now(UTC),
        ),
    )


class ListCalendarsUseCase:
    def __init__(self, repo: ICalendarRepository) -> None:
        self._repo = repo

    async def execute(self, user_id: str) -> list[Calendar]:
        await ensure_default(self._repo, user_id)
        return await self._repo.list_by_user(user_id)


class CreateCalendarUseCase:
    def __init__(self, repo: ICalendarRepository) -> None:
        self._repo = repo

    async def execute(self, user_id: str, name: str, color: str) -> Calendar:
        await ensure_default(self._repo, user_id)
        existing = await self._repo.list_by_user(user_id)
        if len(existing) >= MAX_CALENDARS:
            raise CalendarLimitExceededException(f"At most {MAX_CALENDARS} calendars.")
        if any(c.name == name for c in existing):
            raise CalendarNameDuplicateException()
        return await self._repo.save(
            Calendar(
                id=generate_id("cal"),
                user_id=user_id,
                name=name,
                color=color,
                sort_order=max((c.sort_order for c in existing), default=0) + 1,
                created_at=datetime.now(UTC),
            )
        )


@dataclass(frozen=True)
class UpdateCalendarCommand:
    user_id: str
    calendar_id: str
    name: str | _Unset = UNSET
    color: str | _Unset = UNSET
    sort_order: int | _Unset = UNSET
    push_to_google: bool | _Unset = UNSET


class UpdateCalendarUseCase:
    def __init__(self, repo: ICalendarRepository) -> None:
        self._repo = repo

    async def execute(self, cmd: UpdateCalendarCommand) -> Calendar:
        calendar = await self._repo.find_by_id(cmd.calendar_id, cmd.user_id)
        if calendar is None:
            raise CalendarNotFoundException()
        changes: dict[str, object] = {}
        for field_name in ("name", "color", "sort_order", "push_to_google"):
            value = getattr(cmd, field_name)
            if not isinstance(value, _Unset):
                changes[field_name] = value
        if "name" in changes and changes["name"] != calendar.name:
            others = await self._repo.list_by_user(cmd.user_id)
            if any(c.name == changes["name"] and c.id != calendar.id for c in others):
                raise CalendarNameDuplicateException()
        return await self._repo.save(
            replace(calendar, **changes, updated_at=datetime.now(UTC))  # type: ignore[arg-type]
        )


class DeleteCalendarUseCase:
    def __init__(self, repo: ICalendarRepository) -> None:
        self._repo = repo

    async def execute(self, user_id: str, calendar_id: str) -> None:
        calendar = await self._repo.find_by_id(calendar_id, user_id)
        if calendar is None:
            raise CalendarNotFoundException()
        if calendar.is_default:
            raise CalendarDefaultUndeletableException()
        await self._repo.delete(calendar_id, user_id)
