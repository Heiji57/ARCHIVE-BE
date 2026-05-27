from app.auth.application.dtos.commands import SendEmailVerificationCommand
from app.auth.domain.exceptions.exceptions import AuthTokenInvalidException
from app.auth.infrastructure.cache.email_verification import EmailVerificationCache
from app.shared.infrastructure.email.smtp import send_email


class SendEmailVerificationUseCase:
    def __init__(self, verification_cache: EmailVerificationCache) -> None:
        self._cache = verification_cache

    async def execute(self, cmd: SendEmailVerificationCommand) -> None:
        if await self._cache.is_on_cooldown(cmd.email):
            raise AuthTokenInvalidException(
                "Please wait before requesting another code."
            )

        code = await self._cache.create_code(cmd.email)
        await send_email(
            to=cmd.email,
            subject="[ARCHIVE] 이메일 인증 코드",
            body=f"인증 코드: {code}\n\n코드는 10분간 유효합니다.",
        )
