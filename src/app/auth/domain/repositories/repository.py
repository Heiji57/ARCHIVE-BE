from abc import ABC, abstractmethod

from app.auth.domain.models.oauth_connection import OAuthConnection
from app.auth.domain.models.refresh_token import RefreshToken
from app.auth.domain.models.value_objects import OAuthProvider


class IOAuthConnectionRepository(ABC):
    @abstractmethod
    async def save(self, connection: OAuthConnection) -> OAuthConnection: ...

    @abstractmethod
    async def find_by_provider(
        self, provider: OAuthProvider, provider_user_id: str
    ) -> OAuthConnection | None: ...

    @abstractmethod
    async def find_by_user_id(self, user_id: str) -> list[OAuthConnection]: ...

    @abstractmethod
    async def delete(self, id: str) -> None: ...


class IRefreshTokenRepository(ABC):
    """PostgreSQL — 감사 로그 / 기기 관리 전용. 검증 hot path는 Redis."""

    @abstractmethod
    async def save(self, token: RefreshToken) -> None: ...

    @abstractmethod
    async def find_by_hash(self, token_hash: str) -> RefreshToken | None: ...

    @abstractmethod
    async def revoke(self, token_hash: str) -> None: ...

    @abstractmethod
    async def revoke_all_by_user(self, user_id: str) -> None: ...
