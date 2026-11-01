import asyncio
from datetime import timedelta
from typing import Protocol


class _ReviewJobProcessor(Protocol):
    async def execute_once(self) -> bool: ...


class ReviewJobWorker:
    def __init__(
        self,
        processor: _ReviewJobProcessor,
        poll_interval: timedelta = timedelta(seconds=5),
    ) -> None:
        if poll_interval <= timedelta():
            raise ValueError("poll_interval must be positive")

        self._processor = processor
        self._poll_interval = poll_interval

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            processed = await self._processor.execute_once()
            if processed:
                continue

            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=self._poll_interval.total_seconds(),
                )
            except asyncio.TimeoutError:
                pass