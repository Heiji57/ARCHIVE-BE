import hashlib

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.calendars.domain.exceptions.exceptions import CalendarNameDuplicateException
from app.calendars.domain.models.calendar import Calendar
from app.calendars.domain.repositories.repository import ICalendarRepository
from app.calendars.infrastructure.persistence.models.calendar_model import CalendarModel
from app.shared.infrastructure.database.errors import translate_unique_violations


class CalendarRepository(ICalendarRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, user_id: str) -> list[Calendar]:
        result = await self._session.execute(
            select(CalendarModel)
            .where(CalendarModel.user_id == user_id)
            .order_by(CalendarModel.sort_order, CalendarModel.created_at)
        )
        return [self._to_entity(m) for m in result.scalars()]

    async def find_by_id(self, calendar_id: str, user_id: str) -> Calendar | None:
        result = await self._session.execute(
            select(CalendarModel).where(
                CalendarModel.id == calendar_id, CalendarModel.user_id == user_id
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def find_default(self, user_id: str) -> Calendar | None:
        result = await self._session.execute(
            select(CalendarModel).where(
                CalendarModel.user_id == user_id, CalendarModel.is_default.is_(True)
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def ensure_default(self, user_id: str, default: Calendar) -> Calendar:
        # 마이그레이션 043 과 같은 결정적 id — 동시 요청이 같은 행을 노리게 해 충돌을 무시한다.
        values = {
            c.name: getattr(self._to_model(default), c.name) for c in CalendarModel.__table__.c
        }
        values["id"] = "cal_default_" + hashlib.md5(user_id.encode()).hexdigest()
        await self._session.execute(insert(CalendarModel).values(**values).on_conflict_do_nothing())
        found = await self.find_default(user_id)
        assert found is not None
        return found

    async def save(self, calendar: Calendar) -> Calendar:
        # 사전 중복 검사를 동시 요청이 함께 통과해도 늦은 쪽은 500 이 아니라 409.
        async with translate_unique_violations(
            {"uq_calendars_user_name": CalendarNameDuplicateException}
        ):
            merged = await self._session.merge(self._to_model(calendar))
            await self._session.flush()
        return self._to_entity(merged)

    async def delete(self, calendar_id: str, user_id: str) -> None:
        await self._session.execute(
            delete(CalendarModel).where(
                CalendarModel.id == calendar_id, CalendarModel.user_id == user_id
            )
        )

    @staticmethod
    def _to_model(c: Calendar) -> CalendarModel:
        return CalendarModel(
            id=c.id,
            user_id=c.user_id,
            name=c.name,
            color=c.color,
            sort_order=c.sort_order,
            is_default=c.is_default,
            push_to_google=c.push_to_google,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )

    @staticmethod
    def _to_entity(m: CalendarModel) -> Calendar:
        return Calendar(
            id=m.id,
            user_id=m.user_id,
            name=m.name,
            color=m.color,
            sort_order=m.sort_order,
            is_default=m.is_default,
            push_to_google=m.push_to_google,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
