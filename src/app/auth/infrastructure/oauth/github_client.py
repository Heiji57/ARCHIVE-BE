from urllib.parse import urlencode

import httpx

from app.auth.domain.exceptions.exceptions import OAuthStateInvalidException
from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.infrastructure.oauth.client import IOAuthClient, OAuthUserInfo
from app.shared.infrastructure.config.oauth import GitHubOAuthConfig


class GitHubOAuthClient(IOAuthClient):
    _AUTH_URL = "https://github.com/login/oauth/authorize"
    _TOKEN_URL = "https://github.com/login/oauth/access_token"
    _USER_URL = "https://api.github.com/user"
    _EMAILS_URL = "https://api.github.com/user/emails"

    def __init__(self, config: GitHubOAuthConfig) -> None:
        self._config = config

    @property
    def provider(self) -> OAuthProvider:
        return OAuthProvider.GITHUB

    def get_authorization_url(self, state: str) -> str:
        params = urlencode({
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            # user:email — verified emails 캐시 (commit author 매칭용)
            # public_repo — 회고록 push 및 commit 조회
            "scope": "user:email,public_repo",
            "state": state,
        })
        return f"{self._AUTH_URL}?{params}"

    async def exchange_code(self, code: str) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._TOKEN_URL,
                headers={"Accept": "application/json"},
                json={
                    "client_id": self._config.client_id,
                    "client_secret": self._config.client_secret,
                    "code": code,
                    "redirect_uri": self._config.redirect_uri,
                },
            )
        data = response.json()
        if "error" in data:
            raise OAuthStateInvalidException()
        return data["access_token"]

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        }
        async with httpx.AsyncClient() as client:
            user_resp = await client.get(self._USER_URL, headers=headers)
            emails_resp = await client.get(self._EMAILS_URL, headers=headers)

        primary_email = next(
            (e["email"] for e in emails_resp.json() if e["primary"] and e["verified"]),
            None,
        )
        if not primary_email:
            raise OAuthStateInvalidException()

        user_data = user_resp.json()
        return OAuthUserInfo(
            provider_user_id=str(user_data["id"]),
            email=primary_email,
            login=user_data.get("login"),
        )
