import asyncio

from code_review_assistant.infrastructure.database.engine import (
    create_database_engine,
    create_session_factory,
)
from code_review_assistant.settings import Settings


def test_database_engine_uses_postgres_settings_without_exposing_password() -> None:
    settings = Settings(
        _env_file=None,
        postgres_db="review_assistant",
        postgres_user="review_assistant",
        postgres_password="test-password",
        postgres_host="127.0.0.1",
        postgres_port=5432,
    )

    engine = create_database_engine(settings)
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.host == "127.0.0.1"
        assert engine.url.database == "review_assistant"
        assert engine.url.password == "test-password"
        assert "test-password" not in engine.url.render_as_string(
            hide_password=True
        )
        assert create_session_factory(engine).kw["expire_on_commit"] is False
    finally:
        asyncio.run(engine.dispose())