"""Google Calendar 자동 보내기 판단 — 생성과 휴지통 복원이 같은 규칙을 쓴다.

`calendar_auto_push_todo` 가 켜져 있고, 그 할 일의 캘린더가 Google 보내기를 켠 경우에만
(기본: 기본 캘린더만 — 08 §2).
"""

from app.calendars.domain.repositories.repository import ICalendarRepository
from app.settings.domain.repositories.repository import IUserSettingsRepository


async def auto_push_enabled(
    settings_repo: IUserSettingsRepository,
    calendar_repo: ICalendarRepository | None,
    user_id: str,
    calendar_id: str | None,
) -> bool:
    settings = await settings_repo.find_by_user_id(user_id)
    if not (settings and settings.calendar_auto_push_todo):
        return False
    if calendar_repo is None:
        return True
    calendar = (
        await calendar_repo.find_by_id(calendar_id, user_id)
        if calendar_id is not None
        else await calendar_repo.find_default(user_id)
    )
    # 기본 캘린더 행이 아직 없으면(첫 목록 조회 전) 기본값 — 기본 캘린더는 보낸다.
    return calendar.push_to_google if calendar is not None else calendar_id is None
