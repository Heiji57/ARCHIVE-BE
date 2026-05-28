from urllib.parse import urlencode

import httpx

from app.auth.domain.exceptions.exceptions import OAuthStateInvalidException
from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.infrastructure.oauth.client import IOAuthClient, OAuthUserInfo
from app.shared.infrastructure.config.oauth import GoogleOAuthConfig


class GoogleOAuthClient(IOAuthClient):
    _AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN_URL = "https://oauth2.googleapis.com/token"
    _USER_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    def __init__(self, config: GoogleOAuthConfig) -> None:
        self._config = config

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
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._TOKEN_URL,
                json={
                    "client_id": self._config.client_id,
                    "client_secret": self._config.client_secret,
                    "code": code,
                    "redirect_uri": self._config.redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        data = response.json()
        if "error" in data:
            raise OAuthStateInvalidException()
        return data["access_token"]

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self._USER_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        data = response.json()
        if not data.get("verified_email"):
            raise OAuthStateInvalidException()
        return OAuthUserInfo(
            provider_user_id=data["id"],
            email=data["email"],
        )
