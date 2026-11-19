from app.calendars.domain.exceptions.exceptions import CalendarNotFoundException
from app.calendars.domain.repositories.repository import ICalendarRepository


async def check_calendar_owned(
    repo: ICalendarRepository | None, user_id: str, calendar_id: str | None
) -> None:
    """다른 사용자의(또는 없는) 캘린더 id 로 할 일을 만들거나 옮기지 못하게 한다(404).

    None 은 기본 캘린더라 검사하지 않는다.
    """
    if repo is None or calendar_id is None:
        return
    if await repo.find_by_id(calendar_id, user_id) is None:
        raise CalendarNotFoundException()
