import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool

from app.shared.infrastructure.database.base import Base

# 모든 ORM 모델을 import해야 autogenerate가 인식한다
import app.user.infrastructure.persistence.models.user_model  # noqa: F401
import app.user.infrastructure.persistence.models.country_history_model  # noqa: F401
import app.todo.infrastructure.persistence.models.todo_model  # noqa: F401
import app.retrospective.infrastructure.persistence.models.journal_entry_model  # noqa: F401
import app.retrospective.infrastructure.persistence.models.retro_summary_model  # noqa: F401
import app.notification.infrastructure.persistence.models.notification_model  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# pydantic-settings가 .env를 자동으로 로드하므로 별도 의존성 없이 DB URL을 읽어온다
from app.shared.infrastructure.config.settings import get_settings as _get_settings
config.set_main_option("sqlalchemy.url", _get_settings().db.url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
