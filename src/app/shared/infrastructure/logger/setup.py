"""structlog 초기화 — API·워커 공통, 프로세스당 한 번.

- structlog 와 stdlib 로거(uvicorn·celery·sqlalchemy 등)를 같은 JSON 한 줄 포맷으로 stdout 에 쓴다.
  컨테이너 로그 수집기가 한 형식만 파싱하면 되고, request_id/task_id 로 서비스 간 추적이 된다.
- contextvars(request_id, user_id, task_id …)가 모든 로그 줄에 자동으로 붙는다.
- 레벨은 env `LOG_LEVEL`(기본 INFO).

예전에는 security logger 를 처음 가져올 때만 설정돼, 그 전의 로그와 워커 로그는 포맷이 달랐다.
"""
import logging
import os
import sys

import structlog

_CONFIGURED = False

# INFO 에서 요청 URL 을 통째로 남긴다 — Calendar syncToken/pageToken 같은 쿼리 파라미터가 로그에
# 새지 않도록 WARNING 이상만.
_QUIET_LOGGERS = ("httpx", "httpcore")


def configure_logging(level: str | None = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level_name = (level or os.environ.get("LOG_LEVEL") or "INFO").upper()

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level_name)

    # uvicorn/celery 가 자체 핸들러를 달아 두면 같은 줄이 다른 포맷으로 두 번 찍힌다.
    # 핸들러를 떼고 루트로 모은다.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery", "celery.app.trace"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    _CONFIGURED = True
