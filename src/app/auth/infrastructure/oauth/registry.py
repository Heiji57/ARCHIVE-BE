from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.infrastructure.oauth.client import IOAuthClient


class OAuthClientRegistry:
    def __init__(self, clients: dict[OAuthProvider, IOAuthClient]) -> None:
        self._clients = clients

    def get(self, provider: OAuthProvider) -> IOAuthClient:
        return self._clients[provider]
