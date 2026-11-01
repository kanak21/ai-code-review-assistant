import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import URL, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from code_review_assistant.settings import Settings
from code_review_assistant.infrastructure.database.base import Base
from code_review_assistant.infrastructure.database.standard_record import StandardRecord
from code_review_assistant.infrastructure.database.standard_embedding_record import (
    StandardEmbeddingRecord,
)
from code_review_assistant.infrastructure.database.github_installation_record import (
    GitHubInstallationRecord,
)

from code_review_assistant.infrastructure.database.review_job_record import (
    ReviewJobRecord,
)

from code_review_assistant.infrastructure.database.review_record import (
    ReviewRecord,
)

from code_review_assistant.infrastructure.database.review_finding_record import (
    ReviewFindingRecord,
)
from code_review_assistant.infrastructure.database.review_check_record import (
    ReviewCheckRecord,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = Settings()
database_url = URL.create(
    drivername="postgresql+psycopg",
    username=settings.postgres_user,
    password=settings.postgres_password.get_secret_value(),
    host=settings.postgres_host,
    port=settings.postgres_port,
    database=settings.postgres_db,
)
config.set_main_option(
    "sqlalchemy.url",
    database_url.render_as_string(hide_password=False).replace("%", "%%"),
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(
        run_migrations_online(),
        loop_factory=asyncio.SelectorEventLoop,
    )