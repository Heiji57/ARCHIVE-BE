"""비밀번호 재설정 요청 — 항상 200 반환 (이메일 enumeration 방지).

내부 분기:
- 이메일이 DB에 없음 → silent skip
- OAuth 전용 사용자 (password_hash IS NULL) → silent skip
- 쿨다운 중 → silent skip
- 정상 → 토큰 생성 + 이메일 발송
"""
from app.auth.application.dtos.commands import RequestPasswordResetCommand
from app.auth.infrastructure.cache.password_reset import PasswordResetCache
from app.shared.infrastructure.config.settings import get_settings
from app.shared.infrastructure.email.smtp import send_email
from app.shared.infrastructure.email.templates import render_email
from app.user.domain.repositories.repository import IUserRepository


class RequestPasswordResetUseCase:
    def __init__(
        self,
        user_repo: IUserRepository,
        cache: PasswordResetCache,
    ) -> None:
        self._user_repo = user_repo
        self._cache = cache

    async def execute(self, cmd: RequestPasswordResetCommand) -> None:
        # 이메일 case는 register/login과 동일하게 strip만 (lowercase 없음 — 가입 시점 보존)
        email = cmd.email.strip()
        if await self._cache.is_on_cooldown(email):
            return

        user = await self._user_repo.find_by_email(email)
        if user is None:
            return
        if user.password_hash is None:
            # OAuth 전용 — 비밀번호 자체가 없음. 안내 메일도 보내지 않음
            return

        token = await self._cache.create_token(user.id, email)
        settings = get_settings()
        expires_minutes = settings.auth.password_reset_ttl_seconds // 60
        reset_url = (
            f"{settings.frontend_url.rstrip('/')}/reset-password?token={token}"
        )

        html_body = render_email(
            "password_reset.html",
            reset_url=reset_url,
            expires_minutes=expires_minutes,
        )
        text_body = (
            "ARCHIVE 비밀번호 재설정 안내\n\n"
            f"아래 링크를 눌러 비밀번호를 재설정해 주세요. ({expires_minutes}분 유효)\n\n"
            f"{reset_url}\n\n"
            "본인이 요청하지 않았다면 이 메일을 무시해 주세요."
        )

        await send_email(
            to=email,
            subject="[ARCHIVE] 비밀번호 재설정 안내",
            body=text_body,
            html_body=html_body,
        )
