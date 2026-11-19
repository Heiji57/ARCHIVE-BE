from dataclasses import dataclass

from app.shared.domain.models.base import BaseEntity


@dataclass(kw_only=True)
class UserTag(BaseEntity):
    """태그의 색·순서만 담는 보조 정보. 태그 자체는 `todos.tags` 배열에 있다.

    행이 없는 태그는 FE 가 이름 해시 색을 쓰고, 순서는 사용 횟수 순이다.
    """

    user_id: str
    name: str
    color: str | None = None  # FE 팔레트 키 c1~c8
    sort_order: int | None = None


@dataclass(frozen=True)
class TagSummary:
    """`GET /todos/tags` 한 줄 — 사용 중인 태그 + 보조 정보."""

    name: str
    count: int  # 그 태그가 붙은 할 일 수(반복 시리즈는 base 한 건)
    color: str | None
    sort_order: int | None
