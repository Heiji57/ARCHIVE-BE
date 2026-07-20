"""회고 템플릿 표준 기본 본문 (canonical default content).

reset 엔드포인트 및 회원가입 시드에 사용.
FE의 defaults.ts 와 동일한 내용으로 유지한다.
"""
from app.retrospective.domain.models.value_objects import RetroType

DEFAULT_NAMES: dict[RetroType, str] = {
    RetroType.DAILY: "기본 일간 템플릿",
    RetroType.WEEKLY: "기본 주간 템플릿",
    RetroType.MONTHLY: "기본 월간 템플릿",
    RetroType.YEARLY: "기본 연간 템플릿",
}

DEFAULT_CONTENT: dict[RetroType, str] = {
    RetroType.DAILY: (
        "## 오늘 한 일\n\n"
        "## 배운 것\n\n"
        "## 내일 할 일\n\n"
        "## 느낀 점"
    ),
    RetroType.WEEKLY: (
        "## 이번 주 한 일\n\n"
        "## 배운 것\n\n"
        "## 다음 주 목표\n\n"
        "## 느낀 점"
    ),
    RetroType.MONTHLY: (
        "## 이번 달 성과\n\n"
        "## 배운 것\n\n"
        "## 다음 달 목표\n\n"
        "## 회고"
    ),
    RetroType.YEARLY: (
        "## 올해 성과\n\n"
        "## 배운 것\n\n"
        "## 내년 목표\n\n"
        "## 회고"
    ),
}
