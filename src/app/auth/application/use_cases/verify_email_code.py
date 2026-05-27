from app.auth.application.dtos.commands import VerifyEmailCodeCommand
from app.auth.infrastructure.cache.email_verification import EmailVerificationCache


class VerifyEmailCodeUseCase:
    def __init__(self, verification_cache: EmailVerificationCache) -> None:
        self._cache = verification_cache

    async def execute(self, cmd: VerifyEmailCodeCommand) -> None:
        await self._cache.verify_code(cmd.email, cmd.code)
