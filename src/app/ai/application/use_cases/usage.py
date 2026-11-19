"""AI 사용량 — 사용자별 하루·한 달 요청 수(사용자 tz 날짜). 규칙 기반 추천은 세지 않는다."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.ai.domain.exceptions.exceptions import AiUsageLimitExceededException
from app.ai.domain.models.suggestion import AiUsageReport
from app.ai.domain.repositories.repository import IAiUsageRepository
from app.user.domain.repositories.repository import IUserRepository


class AiUsageService:
    def __init__(
        self,
        repo: IAiUsageRepository,
        user_repo: IUserRepository,
        day_limit: int,
        month_limit: int,
    ) -> None:
        self._repo = repo
        self._user_repo = user_repo
        self._day_limit = day_limit
        self._month_limit = month_limit

    async def _today(self, user_id: str, now: datetime | None) -> str:
        user = await self._user_repo.find_by_id(user_id)
        tz = ZoneInfo(user.timezone if user else "UTC")
        return (now or datetime.now(UTC)).astimezone(tz).date().isoformat()

    async def report(self, user_id: str, now: datetime | None = None) -> AiUsageReport:
        today = await self._today(user_id, now)
        return AiUsageReport(
            day_used=await self._repo.requests_on(user_id, today),
            day_limit=self._day_limit,
            month_used=await self._repo.requests_in_month(user_id, today[:7]),
            month_limit=self._month_limit,
        )

    async def check(self, user_id: str, now: datetime | None = None) -> None:
        """한 번 더 부를 수 있는지. 넘으면 429 AI_USAGE_LIMIT_EXCEEDED."""
        r = await self.report(user_id, now)
        for scope, used, limit in (
            ("day", r.day_used, r.day_limit),
            ("month", r.month_used, r.month_limit),
        ):
            if used >= limit:
                raise AiUsageLimitExceededException(
                    f"AI {scope} quota exceeded.",
                    details=[{"scope": scope, "used": used, "limit": limit}],
                )

    async def record(
        self, user_id: str, input_tokens: int, output_tokens: int, now: datetime | None = None
    ) -> None:
        today = await self._today(user_id, now)
        await self._repo.add(user_id, today, 1, input_tokens, output_tokens)


class GetAiUsageUseCase:
    def __init__(self, usage: AiUsageService) -> None:
        self._usage = usage

    async def execute(self, user_id: str) -> AiUsageReport:
        return await self._usage.report(user_id)
