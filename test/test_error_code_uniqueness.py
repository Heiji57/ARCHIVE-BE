"""도메인 예외 코드는 하나의 HTTP 상태로만 매핑돼야 한다.

`_STATUS_MAP` 은 코드 문자열이 키라, 두 예외 클래스가 같은 코드를 쓰면 뒤에 적힌 매핑이
앞의 것을 조용히 덮는다(AI 사용량 429 가 Gemini 쿼터 503 에 덮였던 사례).
"""
from collections import defaultdict

import app.main  # noqa: F401  (모든 라우터·예외 모듈 import)
from app.shared.domain.exceptions.base import BaseAppException


def _all_subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from _all_subclasses(sub)


def test_each_error_code_belongs_to_one_exception_class():
    by_code = defaultdict(set)
    for exc in _all_subclasses(BaseAppException):
        # 같은 코드를 물려받기만 한 하위 클래스(코드 재정의 없음)는 같은 예외로 본다.
        if "code" in exc.__dict__:
            by_code[exc.code].add(f"{exc.__module__}.{exc.__qualname__}")
    duplicated = {code: names for code, names in by_code.items() if len(names) > 1}
    assert duplicated == {}
