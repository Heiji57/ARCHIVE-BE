from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.auth.domain.models.value_objects import OAuthProvider


@dataclass
class OAuthUserInfo:
    provider_user_id: str
    email: str
    login: str | None = None    # provider 사용자명 (GitHub `login` 등). 없는 provider 는 None.


class IOAuthClient(ABC):
    @property
    @abstractmethod
    def provider(self) -> OAuthProvider: ...

    @abstractmethod
    def get_authorization_url(self, state: str) -> str: ...

    @abstractmethod
    async def exchange_code(self, code: str) -> str: ...

    @abstractmethod
    async def get_user_info(self, access_token: str) -> OAuthUserInfo: ...
