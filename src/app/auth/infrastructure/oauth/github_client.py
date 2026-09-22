from urllib.parse import urlencode

import httpx

from app.auth.domain.exceptions.exceptions import (
    OAuthEmailNotVerifiedException,
    OAuthProviderResponseInvalidException,
)
from app.auth.domain.models.value_objects import OAuthProvider
from app.auth.infrastructure.oauth import http
from app.auth.infrastructure.oauth.client import IOAuthClient, OAuthUserInfo
from app.shared.infrastructure.config.oauth import GitHubOAuthConfig


class GitHubOAuthClient(IOAuthClient):
    _AUTH_URL = "https://github.com/login/oauth/authorize"
    _TOKEN_URL = "https://github.com/login/oauth/access_token"
    _USER_URL = "https://api.github.com/user"
    _EMAILS_URL = "https://api.github.com/user/emails"

    def __init__(
        self,
        config: GitHubOAuthConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport  # 테스트용 주입 지점 (기본: 실제 네트워크)

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
        response = await http.send(
            "github",
            "POST",
            self._TOKEN_URL,
            transport=self._transport,
            headers={"Accept": "application/json"},
            json={
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "code": code,
                "redirect_uri": self._config.redirect_uri,
            },
        )
        return http.token_from_exchange("github", response)

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        }
        user_resp = await http.send(
            "github", "GET", self._USER_URL, transport=self._transport, headers=headers
        )
        http.ensure_ok("github", user_resp)
        emails_resp = await http.send(
            "github", "GET", self._EMAILS_URL, transport=self._transport, headers=headers
        )
        http.ensure_ok("github", emails_resp)

        user_data = http.parse_json("github", user_resp)
        emails = http.parse_json("github", emails_resp)
        if not isinstance(user_data, dict) or not isinstance(emails, list):
            raise OAuthProviderResponseInvalidException("github user/emails: unexpected shape")
        if user_data.get("id") is None:
            raise OAuthProviderResponseInvalidException("github user: missing id")

        primary_email = next(
            (
                e.get("email")
                for e in emails
                if isinstance(e, dict) and e.get("primary") and e.get("verified")
            ),
            None,
        )
        if not primary_email:
            raise OAuthEmailNotVerifiedException()

        return OAuthUserInfo(
            provider_user_id=str(user_data["id"]),
            email=primary_email,
            login=user_data.get("login"),
        )
