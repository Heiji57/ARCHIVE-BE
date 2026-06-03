from app.auth.application.dtos.commands import SendEmailVerificationCommand
from app.auth.domain.exceptions.exceptions import AuthTokenInvalidException
from app.auth.infrastructure.cache.email_verification import EmailVerificationCache
from app.shared.infrastructure.config.settings import get_settings
from app.shared.infrastructure.email.smtp import send_email
from app.shared.infrastructure.email.templates import render_email


class SendEmailVerificationUseCase:
    def __init__(self, verification_cache: EmailVerificationCache) -> None:
        self._cache = verification_cache

    async def execute(self, cmd: SendEmailVerificationCommand) -> None:
        if await self._cache.is_on_cooldown(cmd.email):
            raise AuthTokenInvalidException("Please wait before requesting another code.")

        code = await self._cache.create_code(cmd.email)
        settings = get_settings()
        expires_minutes = settings.auth.email_verify_code_ttl_seconds // 60
        copy_url = f"{settings.api_base_url.rstrip('/')}/static/emails/copy.html?code={code}"

        html_body = render_email(
            "verification_code.html",
            code=code,
            expires_minutes=expires_minutes,
            copy_url=copy_url,
        )
        text_body = (
            f"ARCHIVE 이메일 인증\n\n"
            f"인증 코드: {code}\n\n"
            f"이 코드는 {expires_minutes}분간 유효합니다.\n\n"
            f"본인이 요청하지 않았다면 이 메일을 무시해 주세요."
        )

        await send_email(
            to=cmd.email,
            subject="[ARCHIVE] 이메일 인증 코드",
            body=text_body,
            html_body=html_body,
        )
