"""사용자의 AI 요약 생성 사용량 조회.

`POST /summaries/generate` 호출 전 FE 가 버튼 활성/비활성을 결정하거나,
남은 한도를 표시하는 용도. record 하지 않고 단순 조회만.
"""
from dataclasses import dataclass

from app.retrospective.domain.models.value_objects import SummaryType
from app.retrospective.infrastructure.cache.summary_rate_limiter import (
    SummaryRateLimiter,
    UsageState,
)


@dataclass(frozen=True)
class SummaryUsageReport:
    weekly: UsageState
    monthly: UsageState
    annual: UsageState


class GetSummaryUsageUseCase:
    def __init__(self, rate_limiter: SummaryRateLimiter) -> None:
        self._rate_limiter = rate_limiter

    async def execute(self, user_id: str) -> SummaryUsageReport:
        weekly = await self._rate_limiter.get_usage(user_id, SummaryType.WEEKLY)
        monthly = await self._rate_limiter.get_usage(user_id, SummaryType.MONTHLY)
        annual = await self._rate_limiter.get_usage(user_id, SummaryType.ANNUAL)
        return SummaryUsageReport(weekly=weekly, monthly=monthly, annual=annual)
