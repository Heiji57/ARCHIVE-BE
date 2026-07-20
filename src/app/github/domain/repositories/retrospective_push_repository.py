from abc import ABC, abstractmethod

from app.github.domain.models.retrospective_push import RetrospectivePush


class IRetrospectivePushRepository(ABC):
    @abstractmethod
    async def upsert(self, push: RetrospectivePush) -> RetrospectivePush:
        """동일 (user_id, period_type, period_key) row 가 있으면 갱신, 없으면 신규."""

    @abstractmethod
    async def find_by_period(
        self, user_id: str, period_type: str, period_key: str
    ) -> RetrospectivePush | None: ...

    @abstractmethod
    async def find_many(
        self,
        user_id: str,
        keys: list[tuple[str, str]],     # [(period_type, period_key), ...]
    ) -> list[RetrospectivePush]:
        """여러 (period_type, period_key) 를 한 번에 조회 (batch). list/get enrich 용."""
