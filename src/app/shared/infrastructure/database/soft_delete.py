"""휴지통(soft delete) — `deleted_at` 이 채워진 행을 모든 ORM 조회에서 자동으로 뺀다.

할 일·회고·사용자를 지우면 행을 지우지 않고 `deleted_at` 을 채운다. 조회마다 조건을 붙이면
한 곳이라도 빠뜨리는 순간 지운 것이 새어 나오므로, 세션의 `do_orm_execute` 에서
`with_loader_criteria` 로 일괄 적용한다(SQLAlchemy 의 표준 soft delete 패턴). 엔티티·컬럼
선택, `session.get`, ORM UPDATE/DELETE, 조인 모두에 걸린다.

- 휴지통 목록·복원·영구 삭제처럼 지운 행을 다뤄야 하는 쿼리만 `INCLUDE_DELETED` 를 붙인다.
- **raw `text()` SQL 에는 걸리지 않는다** — 그런 쿼리는 직접 `deleted_at IS NULL` 을 쓴다.
"""

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

INCLUDE_DELETED: dict[str, Any] = {"include_deleted": True}

_SOFT_DELETABLE: list[type] = []


def register(model: type) -> type:
    """deleted_at 컬럼이 있는 ORM 모델을 등록한다(모델 정의 뒤 호출)."""
    _SOFT_DELETABLE.append(model)
    return model


@event.listens_for(Session, "do_orm_execute")
def _exclude_deleted(state: ORMExecuteState) -> None:
    if not (state.is_select or state.is_update or state.is_delete):
        return
    if state.execution_options.get("include_deleted", False):
        return
    for model in _SOFT_DELETABLE:
        state.statement = state.statement.options(
            with_loader_criteria(model, lambda cls: cls.deleted_at.is_(None), include_aliases=True)
        )
