"""사용자 locale별 폴더/파일명/커밋 메시지 템플릿.

지원: ko, en. 미지원 locale은 en으로 fallback.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PathLabels:
    daily_folder: str
    weekly_folder: str
    monthly_folder: str
    annual_folder: str
    daily_filename: str    # {date}
    weekly_filename: str   # {year}-{month:02d} {week}주차/{week}
    monthly_filename: str  # {year}-{month:02d}
    annual_filename: str   # {year}


_LABELS: dict[str, PathLabels] = {
    "ko": PathLabels(
        daily_folder="일간",
        weekly_folder="주간",
        monthly_folder="월간",
        annual_folder="년간",
        daily_filename="{date} 회고록",
        weekly_filename="{year}-{month:02d} {week}주차 회고록",
        monthly_filename="{year}-{month:02d} 회고록",
        annual_filename="{year} 회고록",
    ),
    "en": PathLabels(
        daily_folder="daily",
        weekly_folder="weekly",
        monthly_folder="monthly",
        annual_folder="annual",
        daily_filename="{date} retrospective",
        weekly_filename="{year}-{month:02d} week {week} retrospective",
        monthly_filename="{year}-{month:02d} retrospective",
        annual_filename="{year} retrospective",
    ),
}


def get_labels(locale: str) -> PathLabels:
    return _LABELS.get(locale, _LABELS["en"])
