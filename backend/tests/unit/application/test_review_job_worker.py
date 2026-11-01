import asyncio
from datetime import timedelta

from code_review_assistant.application.services.review_job_worker import (
    ReviewJobWorker,
)


class EmptyProcessor:
    def __init__(self) -> None:
        self.called = asyncio.Event()
        self.calls = 0

    async def execute_once(self) -> bool:
        self.calls += 1
        self.called.set()
        return False


def test_worker_stops_while_waiting_after_empty_poll() -> None:
    async def verify() -> None:
        processor = EmptyProcessor()
        stop_event = asyncio.Event()
        worker = ReviewJobWorker(
            processor,
            poll_interval=timedelta(seconds=30),
        )

        task = asyncio.create_task(worker.run(stop_event))
        await processor.called.wait()
        stop_event.set()
        await asyncio.wait_for(task, timeout=1)

        assert processor.calls == 1

    asyncio.run(verify())