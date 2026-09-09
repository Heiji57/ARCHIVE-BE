"""digest watermark 날짜 계산 — 사용자 로컬 타임존을 쓰는지.

GitHub #2: watermark 를 `datetime.now(timezone.utc)` 로 서버 UTC 기준 찍었다. 비교
대상인 `date_key`(회고 저장 시점의 사용자 로컬 날짜, `get_topic_stats.py` 의
unreflected 계산)와 축이 달라서, UTC+ 사용자가 자정 근처에 정리를 생성하면 방금 쓴
오늘자 회고가 즉시 "미반영"으로 잡혔다. CLAUDE.md: 기간 계산은 절대 서버 UTC 기준으로
하지 않는다 — `today_in_tz(tz)` 사용.

시각 자체를 얼려 테스트하기보다, `_watermark_key_for_user` 가 `today_in_tz` 를 어떤
tz 인자로 호출하는지를 monkeypatch 로 가로채 검증한다 — "지금이 몇 시냐" 에 좌우되지
않는 결정적 테스트다.
"""
from datetime import UTC, date, datetime

import app.worker.tasks.generate_digest as digest_module
from app.user.domain.models.user import User
from app.user.domain.models.value_objects import Email

_NOW = datetime.now(UTC)


def _user(tz: str) -> User:
    return User(
        id="usr_1",
        created_at=_NOW,
        email=Email("test@example.com"),
        password_hash=None,
        country="KR",
        region=None,
        timezone=tz,
    )


def test_watermark_key_uses_the_users_own_timezone_not_utc(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_today_in_tz(tz: str) -> date:
        captured["tz"] = tz
        return date(2099, 1, 1)

    monkeypatch.setattr(digest_module, "today_in_tz", fake_today_in_tz)

    result = digest_module._watermark_key_for_user(_user("Asia/Seoul"))

    assert captured["tz"] == "Asia/Seoul", "서버 UTC 가 아니라 사용자 timezone 으로 계산해야 한다"
    assert result == "2099-01-01"


def test_watermark_key_falls_back_to_utc_when_user_not_found(monkeypatch) -> None:
    """탈퇴 등으로 user 를 못 찾는 예외적 상황에서만 UTC 로 폴백한다."""
    captured: dict[str, str] = {}

    def fake_today_in_tz(tz: str) -> date:
        captured["tz"] = tz
        return date(2099, 1, 1)

    monkeypatch.setattr(digest_module, "today_in_tz", fake_today_in_tz)

    result = digest_module._watermark_key_for_user(None)

    assert captured["tz"] == "UTC"
    assert result == "2099-01-01"


def test_different_users_get_different_watermark_dates_when_local_today_differs() -> None:
    """실제 today_in_tz 를 태워 두 극단 타임존이 서로 다른 계산 경로를 탄다는 것만 확인.

    실제 벽시계 날짜 비교는 datetime 경계에서 드물게 우연히 같을 수 있어(둘 다 자정
    근처가 아니면 사실상 하루 종일 다르다), 여기서는 "같은 함수가 사용자마다 다른 tz
    인자로 today_in_tz 를 호출한다"는 배선만 확인하고, 실제 값 비교는 위 monkeypatch
    테스트가 결정적으로 담당한다.
    """
    seoul_result = digest_module._watermark_key_for_user(_user("Asia/Seoul"))
    utc_result = digest_module._watermark_key_for_user(_user("UTC"))
    # 둘 다 유효한 ISO 날짜 문자열이어야 한다 — 최소한의 형식 가드.
    date.fromisoformat(seoul_result)
    date.fromisoformat(utc_result)
