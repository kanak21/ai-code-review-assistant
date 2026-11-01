import asyncio
import signal
from types import FrameType

import httpx

from code_review_assistant.infrastructure.database.engine import (
    create_database_engine,
    create_session_factory,
)
from code_review_assistant.infrastructure.llm.anthropic_client import (
    create_anthropic_client,
)
from code_review_assistant.infrastructure.llm.openai_client import (
    create_openai_client,
)
from code_review_assistant.infrastructure.review_worker_composition import (
    create_review_job_worker,
)
from code_review_assistant.settings import Settings
from contextlib import AsyncExitStack


async def run_worker() -> None:
    settings = Settings()
    engine = create_database_engine(settings)

    try:

        async with httpx.AsyncClient(timeout=30.0) as github_client:
            async with AsyncExitStack() as clients:
                
                openai_client = None
                if settings.embedding_provider == "openai":
                    openai_client = await clients.enter_async_context(
                        create_openai_client(settings)
                    )

                anthropic_client = None
                if settings.review_provider == "anthropic":
                    anthropic_client = await clients.enter_async_context(
                        create_anthropic_client(settings)
                    )

                session_factory = create_session_factory(engine)

                worker = create_review_job_worker(
                    settings,
                    session_factory,
                    github_client,
                    anthropic_client=anthropic_client,
                    openai_client=openai_client,
                    ollama_http_client=github_client,
                )

                stop_event = asyncio.Event()
                loop = asyncio.get_running_loop()
                previous_handlers: dict[signal.Signals, object] = {}

                def request_shutdown(
                    signum: int,
                    frame: FrameType | None,
                ) -> None:
                    loop.call_soon_threadsafe(stop_event.set)

                try:
                    for sig in (signal.SIGINT, signal.SIGTERM):
                        previous_handlers[sig] = signal.signal(
                            sig,
                            request_shutdown,
                        )
                    await worker.run(stop_event)
                finally:
                    for sig, handler in previous_handlers.items():
                        signal.signal(sig, handler)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()