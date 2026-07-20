"""보안 이벤트 전용 logger.

탈취 의심, 무효화, 로그인 실패 등 보안 감사가 필요한 이벤트를 별도 logger로 분리.
운영 환경에서는 이 logger 만 별도 sink (예: SIEM, audit log table) 로 흘릴 수 있다.
"""
import logging
import sys

import structlog

_INITIALIZED = False


def _configure_structlog() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _INITIALIZED = True


def get_security_logger() -> structlog.stdlib.BoundLogger:
    """`security` 채널로 묶인 structlog 로거."""
    _configure_structlog()
    return structlog.get_logger("security")
