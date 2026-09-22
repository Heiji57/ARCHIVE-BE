"""DB 제약 위반 → 도메인 예외 번역.

유스케이스의 사전 중복 체크(check-then-insert)는 동시 요청 사이의 경쟁을 막지 못한다 —
두 요청이 모두 체크를 통과하면 늦은 쪽의 flush 가 unique 제약에 걸려 IntegrityError 로
500 이 된다. 각 repository 가 자기 모듈의 "제약 이름 → 도메인 예외" 매핑을 선언하고
이 컨텍스트로 flush 를 감싸, 경쟁에서 진 요청도 사전 체크와 같은 409 를 받게 한다.
매핑에 없는 제약(FK 등)은 코드/데이터 문제이므로 그대로 전파한다.
"""
import re
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager

from sqlalchemy.exc import IntegrityError

from app.shared.domain.exceptions.base import BaseAppException

_CONSTRAINT_IN_MESSAGE = re.compile(r'constraint "([^"]+)"')


def constraint_name(exc: IntegrityError) -> str | None:
    """asyncpg 는 원본 예외(orig 또는 그 __cause__)에 constraint_name 을 싣는다."""
    orig = exc.orig
    for candidate in (orig, getattr(orig, "__cause__", None)):
        name = getattr(candidate, "constraint_name", None)
        if isinstance(name, str) and name:
            return name
    match = _CONSTRAINT_IN_MESSAGE.search(str(orig))
    return match.group(1) if match else None


@asynccontextmanager
async def translate_unique_violations(
    mapping: Mapping[str, type[BaseAppException]],
) -> AsyncIterator[None]:
    try:
        yield
    except IntegrityError as e:
        exc_type = mapping.get(constraint_name(e) or "")
        if exc_type is None:
            raise
        raise exc_type() from e
