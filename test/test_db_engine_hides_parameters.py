"""DB 엔진이 SQL 파라미터를 로그에 남기지 않는지.

버그: `echo=config.is_development` 라서 개발 환경이면 SQL echo 가 무조건 켜지고,
파라미터 값이 그대로 찍혔다 — `/api/v1/calendar/callback` 로그에 Google access/
refresh token 이 평문으로 남아 있었다. echo 는 명시적 opt-in(`DATABASE_ECHO`)으로
바꾸고, 켜더라도 `hide_parameters=True` 로 값은 가린다.
"""
from app.shared.infrastructure.config.database import DatabaseConfig
from app.shared.infrastructure.container.providers import AppProvider

_URL = "postgresql+asyncpg://u:p@localhost/db"


class _Config:
    """AppConfig 중 session_factory 가 쓰는 부분만."""

    def __init__(self, echo: bool) -> None:
        self.db = DatabaseConfig(url=_URL, echo=echo)


def _engine(echo: bool):
    factory = AppProvider().session_factory(_Config(echo))  # type: ignore[arg-type]
    return factory.kw["bind"]


def test_echo_is_off_by_default() -> None:
    assert DatabaseConfig(url=_URL).echo is False
    assert _engine(False).echo is False


def test_parameters_are_hidden_even_when_echo_is_on() -> None:
    engine = _engine(True)
    assert engine.echo is True
    assert engine.sync_engine.hide_parameters is True
