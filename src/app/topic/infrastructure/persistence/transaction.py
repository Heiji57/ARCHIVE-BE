from contextlib import AbstractAsyncContextManager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.topic.domain.repositories.repository import ITopicMatchTransaction


class SqlAlchemyTopicMatchTransaction(ITopicMatchTransaction):
    """`ITopicMatchTransaction` 을 SQLAlchemy SAVEPOINT(`session.begin_nested()`)로 구현.

    DI 는 이 세션을 다른 리포지터리(entry/todo/chunk 등)와 동일한 요청 스코프
    `AsyncSession` 으로 주입한다(`providers.py` 의 `db_session` 은 `Scope.REQUEST`) —
    그래야 `TopicMatcher` 가 여는 SAVEPOINT 가 그 리포지터리들이 실제로 쓰는 트랜잭션
    위에서 동작한다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def nested(self) -> AbstractAsyncContextManager[Any]:
        return self._session.begin_nested()
