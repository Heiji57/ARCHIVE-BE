"""보안 이벤트 전용 logger.

탈취 의심, 무효화, 로그인 실패 등 보안 감사가 필요한 이벤트를 별도 logger로 분리.
운영 환경에서는 이 logger 만 별도 sink (예: SIEM, audit log table) 로 흘릴 수 있다.
"""
import structlog

from app.shared.infrastructure.logger.setup import configure_logging


def get_security_logger() -> structlog.stdlib.BoundLogger:
    """`security` 채널로 묶인 structlog 로거."""
    configure_logging()  # 멱등 — 앱/워커 부팅에서 이미 설정됐으면 no-op
    return structlog.get_logger("security")  # type: ignore[no-any-return]
