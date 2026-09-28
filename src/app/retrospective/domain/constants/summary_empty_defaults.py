"""소스(회고·할일)가 없는 기간의 요약 본문.

AI 를 호출하지 않고 이 문구로 요약을 완료한다. 언어는 `user_settings.locale` 을 따르며,
매핑이 없는 locale 은 en 으로 폴백한다(`entry_title_defaults.py` 와 같은 컨벤션).
"""

_EMPTY_SUMMARY_TEXT: dict[str, str] = {
    "ko": "이 기간에 기록된 회고가 없습니다.",
    "en": "No retrospectives were recorded in this period.",
    "ja": "この期間に記録された振り返りはありません。",
    "zh": "此期间没有记录的回顾。",
}


def empty_summary_text(locale: str | None) -> str:
    base = locale.split("-")[0].split("_")[0].strip().lower() if locale else "en"
    return _EMPTY_SUMMARY_TEXT.get(base, _EMPTY_SUMMARY_TEXT["en"])
