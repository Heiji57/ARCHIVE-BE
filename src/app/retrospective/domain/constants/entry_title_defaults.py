"""회고 기본 제목 규칙.

제목을 비워 보내면 서버가 "{date_key} {회고 종류}" 로 채운다. 언어는 사용자
`user_settings.locale` 을 따르며, 매핑이 없는 locale 은 en 으로 폴백한다
(worker/tasks/generate_summary.py 의 `_notification_text` 와 같은 폴백 컨벤션).
"""
from app.retrospective.domain.models.value_objects import RetroType

_TITLE_LABELS: dict[str, dict[RetroType, str]] = {
    "ko": {
        RetroType.DAILY: "일일 회고",
        RetroType.WEEKLY: "주간 회고",
        RetroType.MONTHLY: "월간 회고",
        RetroType.YEARLY: "연간 회고",
    },
    "en": {
        RetroType.DAILY: "Daily Retrospective",
        RetroType.WEEKLY: "Weekly Retrospective",
        RetroType.MONTHLY: "Monthly Retrospective",
        RetroType.YEARLY: "Annual Retrospective",
    },
    "ja": {
        RetroType.DAILY: "デイリー振り返り",
        RetroType.WEEKLY: "ウィークリー振り返り",
        RetroType.MONTHLY: "マンスリー振り返り",
        RetroType.YEARLY: "年間振り返り",
    },
    "zh": {
        RetroType.DAILY: "每日回顾",
        RetroType.WEEKLY: "每周回顾",
        RetroType.MONTHLY: "每月回顾",
        RetroType.YEARLY: "年度回顾",
    },
}


def default_entry_title(date_key: str, retro_type: RetroType, locale: str | None) -> str:
    base = locale.split("-")[0].split("_")[0].strip().lower() if locale else "en"
    labels = _TITLE_LABELS.get(base, _TITLE_LABELS["en"])
    return f"{date_key} {labels[retro_type]}"


def resolve_entry_title(
    title: str | None, date_key: str, retro_type: RetroType, locale: str | None
) -> str:
    """제목이 없거나 공백뿐이면 기본 제목으로 채운다. FE 가 빈 문자열을 보낼 수 있다."""
    if title and title.strip():
        return title
    return default_entry_title(date_key, retro_type, locale)
