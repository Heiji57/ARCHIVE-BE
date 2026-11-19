from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.domain.models.conversation import ChatMessage, Conversation, Proposal
from app.ai.domain.repositories.repository import IConversationRepository, IProposalRepository
from app.ai.infrastructure.persistence.models.conversation_model import (
    AiConversationModel,
    AiMessageModel,
    AiProposalModel,
)


class ConversationRepository(IConversationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, c: Conversation) -> Conversation:
        merged = await self._session.merge(
            AiConversationModel(
                id=c.id,
                user_id=c.user_id,
                title=c.title,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
        )
        await self._session.flush()
        return self._conv(merged)

    async def find_by_id(self, conversation_id: str, user_id: str) -> Conversation | None:
        result = await self._session.execute(
            select(AiConversationModel).where(
                AiConversationModel.id == conversation_id, AiConversationModel.user_id == user_id
            )
        )
        model = result.scalar_one_or_none()
        return self._conv(model) if model else None

    async def list_by_user(self, user_id: str, limit: int = 50) -> list[Conversation]:
        result = await self._session.execute(
            select(AiConversationModel)
            .where(AiConversationModel.user_id == user_id)
            .order_by(
                func.coalesce(AiConversationModel.updated_at, AiConversationModel.created_at).desc()
            )
            .limit(limit)
        )
        return [self._conv(m) for m in result.scalars()]

    async def delete(self, conversation_id: str, user_id: str) -> None:
        await self._session.execute(
            delete(AiConversationModel).where(
                AiConversationModel.id == conversation_id, AiConversationModel.user_id == user_id
            )
        )

    async def add_message(self, m: ChatMessage) -> ChatMessage:
        self._session.add(
            AiMessageModel(
                id=m.id,
                conversation_id=m.conversation_id,
                role=m.role,
                content=m.content,
                tool_calls=list(m.tool_calls),
                context=m.context,
                created_at=m.created_at,
            )
        )
        await self._session.flush()
        return m

    async def list_messages(
        self, conversation_id: str, limit: int | None = None
    ) -> list[ChatMessage]:
        stmt = (
            select(AiMessageModel)
            .where(AiMessageModel.conversation_id == conversation_id)
            .order_by(AiMessageModel.created_at.desc(), AiMessageModel.id.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = list((await self._session.execute(stmt)).scalars())
        rows.reverse()
        return [
            ChatMessage(
                id=r.id,
                conversation_id=r.conversation_id,
                role=r.role,  # type: ignore[arg-type]
                content=r.content,
                tool_calls=list(r.tool_calls or []),
                context=r.context,
                created_at=r.created_at,
            )
            for r in rows
        ]

    @staticmethod
    def _conv(m: AiConversationModel) -> Conversation:
        return Conversation(
            id=m.id,
            user_id=m.user_id,
            title=m.title,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )


class ProposalRepository(IProposalRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, p: Proposal) -> Proposal:
        merged = await self._session.merge(
            AiProposalModel(
                id=p.id,
                user_id=p.user_id,
                conversation_id=p.conversation_id,
                kind=p.kind,
                payload=p.payload,
                status=p.status,
                applied=p.applied,
                created_at=p.created_at,
                updated_at=p.updated_at,
                applied_at=p.applied_at,
            )
        )
        await self._session.flush()
        return self._to_entity(merged)

    async def find_by_id(
        self, proposal_id: str, user_id: str, for_update: bool = False
    ) -> Proposal | None:
        stmt = select(AiProposalModel).where(
            AiProposalModel.id == proposal_id, AiProposalModel.user_id == user_id
        )
        if for_update:
            stmt = stmt.with_for_update()
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_by_conversation(self, conversation_id: str) -> list[Proposal]:
        result = await self._session.execute(
            select(AiProposalModel)
            .where(AiProposalModel.conversation_id == conversation_id)
            .order_by(AiProposalModel.created_at)
        )
        return [self._to_entity(m) for m in result.scalars()]

    @staticmethod
    def _to_entity(m: AiProposalModel) -> Proposal:
        return Proposal(
            id=m.id,
            user_id=m.user_id,
            conversation_id=m.conversation_id,
            kind=m.kind,  # type: ignore[arg-type]
            payload=dict(m.payload),
            status=m.status,  # type: ignore[arg-type]
            applied=m.applied,
            created_at=m.created_at,
            updated_at=m.updated_at,
            applied_at=m.applied_at,
        )
