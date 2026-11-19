from dataclasses import dataclass

from app.shared.domain.models.base import BaseEntity

# FE 팔레트 키 — hex 대신 키로 받아 다크 테마 대비는 FE 가 관리한다.
PALETTE_KEYS = ("c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8")
DEFAULT_CALENDAR_NAME = "default"  # 고정 키 — 표시 이름은 FE 가 locale 로 바꿔 보여 준다
MAX_CALENDARS = 20


@dataclass(kw_only=True)
class Calendar(BaseEntity):
    """사용자 캘린더(개인·팀·스터디 등). 할 일을 묶는 단위.

    `todos.calendar_id` 가 NULL 이면 기본 캘린더 소속이다 — 기본 캘린더 행은 이름·색·
    Google 보내기 여부를 담는 메타일 뿐, 할 일이 그 id 를 가리킬 필요는 없다.
    """

    user_id: str
    name: str
    color: str = "c1"
    sort_order: int = 0
    is_default: bool = False
    # 이 캘린더의 할 일을 Google Calendar 로 보낼지 (기본 캘린더만 기본 true)
    push_to_google: bool = False
