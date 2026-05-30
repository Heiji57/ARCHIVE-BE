from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.shared.infrastructure.config.settings import get_settings

_factory: async_sessionmaker[AsyncSession] | None = None


def get_worker_session_factory() -> async_sessionmaker[AsyncSession]:
    global _factory
    if _factory is None:
        settings = get_settings()
        engine = create_async_engine(settings.db.url, pool_size=20, max_overflow=30)
        _factory = async_sessionmaker(engine, expire_on_commit=False)
    return _factory
