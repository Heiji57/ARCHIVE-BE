from urllib.parse import urlencode

import httpx

from app.auth.domain.exceptions.exceptions import (
    OAuthEmailNotVerifiedException,
    OAuthProviderResponseInvalidException,
)
from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.infrastructure.oauth import http
from app.auth.infrastructure.oauth.client import IOAuthClient, OAuthUserInfo
from app.shared.infrastructure.config.oauth import GoogleOAuthConfig


class GoogleOAuthClient(IOAuthClient):
    _AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN_URL = "https://oauth2.googleapis.com/token"
    _USER_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    def __init__(
        self,
        config: GoogleOAuthConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport  # 테스트용 주입 지점 (기본: 실제 네트워크)

    @property
    def provider(self) -> OAuthProvider:
        return OAuthProvider.GOOGLE

    def get_authorization_url(self, state: str) -> str:
        params = urlencode({
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            "response_type": "code",
            "scope": "openid email",
            "state": state,
        })
        return f"{self._AUTH_URL}?{params}"

    async def exchange_code(self, code: str) -> str:
        response = await http.send(
            "google",
            "POST",
            self._TOKEN_URL,
            transport=self._transport,
            json={
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "code": code,
                "redirect_uri": self._config.redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        return http.token_from_exchange("google", response)

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        response = await http.send(
            "google",
            "GET",
            self._USER_URL,
            transport=self._transport,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        http.ensure_ok("google", response)
        data = http.parse_json("google", response)
        if not isinstance(data, dict):
            raise OAuthProviderResponseInvalidException("google userinfo: not an object")
        if not data.get("verified_email"):
            raise OAuthEmailNotVerifiedException()
        provider_user_id, email = data.get("id"), data.get("email")
        if not provider_user_id or not email:
            raise OAuthProviderResponseInvalidException("google userinfo: missing id/email")
        return OAuthUserInfo(provider_user_id=str(provider_user_id), email=email)
