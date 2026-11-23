from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.domain.models.suggestion import Suggestion
from app.ai.domain.repositories.repository import IAiUsageRepository, ISuggestionRepository
from app.ai.infrastructure.persistence.models.suggestion_model import (
    AiSuggestionModel,
    AiUsageModel,
)


class SuggestionRepository(ISuggestionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_date(self, user_id: str, date_key: str) -> list[Suggestion]:
        result = await self._session.execute(
            select(AiSuggestionModel).where(
                AiSuggestionModel.user_id == user_id, AiSuggestionModel.date_key == date_key
            )
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_by_id(
        self, suggestion_id: str, user_id: str, for_update: bool = False
    ) -> Suggestion | None:
        stmt = select(AiSuggestionModel).where(
            AiSuggestionModel.id == suggestion_id, AiSuggestionModel.user_id == user_id
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def insert_if_absent(self, s: Suggestion) -> Suggestion:
        await self._session.execute(
            insert(AiSuggestionModel)
            .values(
                id=s.id,
                user_id=s.user_id,
                date_key=s.date_key,
                kind=s.kind,
                todo_id=s.todo_id,
                payload=s.payload,
                status=s.status,
                applied=s.applied,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            .on_conflict_do_nothing(constraint="uq_ai_suggestions_key")
        )
        result = await self._session.execute(
            select(AiSuggestionModel)
            .where(
                AiSuggestionModel.user_id == s.user_id,
                AiSuggestionModel.date_key == s.date_key,
                AiSuggestionModel.kind == s.kind,
                AiSuggestionModel.todo_id == s.todo_id,
            )
            .execution_options(populate_existing=True)
        )
        return self._to_entity(result.scalar_one())

    async def save(self, s: Suggestion) -> Suggestion:
        merged = await self._session.merge(
            AiSuggestionModel(
                id=s.id,
                user_id=s.user_id,
                date_key=s.date_key,
                kind=s.kind,
                todo_id=s.todo_id,
                payload=s.payload,
                status=s.status,
                applied=s.applied,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
        )
        await self._session.flush()
        return self._to_entity(merged)

    async def update_payload_if_shown(
        self, suggestion_id: str, user_id: str, payload: dict[str, Any]
    ) -> Suggestion | None:
        # 조건부 UPDATE — 읽어 둔 행 전체를 merge 하면 그사이 커밋된 적용·넘김(status·applied)을
        # 덮어쓴다. 행이 잠겨 있으면(적용 중) 끝날 때까지 기다린 뒤 조건을 다시 본다.
        result = await self._session.execute(
            update(AiSuggestionModel)
            .where(
                AiSuggestionModel.id == suggestion_id,
                AiSuggestionModel.user_id == user_id,
                AiSuggestionModel.status == "shown",
            )
            .values(payload=payload, updated_at=datetime.now(UTC))
            .returning(AiSuggestionModel)
            .execution_options(populate_existing=True, synchronize_session=False)
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row is not None else None

    @staticmethod
    def _to_entity(m: AiSuggestionModel) -> Suggestion:
        return Suggestion(
            id=m.id,
            user_id=m.user_id,
            date_key=m.date_key,
            kind=m.kind,  # type: ignore[arg-type]
            todo_id=m.todo_id,
            payload=dict(m.payload),
            status=m.status,  # type: ignore[arg-type]
            applied=m.applied,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )


class AiUsageRepository(IAiUsageRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def requests_on(self, user_id: str, date_key: str) -> int:
        value = await self._session.scalar(
            select(AiUsageModel.requests).where(
                AiUsageModel.user_id == user_id, AiUsageModel.date_key == date_key
            )
        )
        return int(value or 0)

    async def requests_in_month(self, user_id: str, month_prefix: str) -> int:
        value = await self._session.scalar(
            select(func.coalesce(func.sum(AiUsageModel.requests), 0)).where(
                AiUsageModel.user_id == user_id,
                AiUsageModel.date_key.like(f"{month_prefix}-%"),
            )
        )
        return int(value or 0)

    async def add(
        self, user_id: str, date_key: str, requests: int, input_tokens: int, output_tokens: int
    ) -> None:
        stmt = insert(AiUsageModel).values(
            user_id=user_id,
            date_key=date_key,
            requests=requests,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        await self._session.execute(
            stmt.on_conflict_do_update(
                index_elements=[AiUsageModel.user_id, AiUsageModel.date_key],
                set_={
                    "requests": AiUsageModel.requests + stmt.excluded.requests,
                    "input_tokens": AiUsageModel.input_tokens + stmt.excluded.input_tokens,
                    "output_tokens": AiUsageModel.output_tokens + stmt.excluded.output_tokens,
                },
            )
        )
