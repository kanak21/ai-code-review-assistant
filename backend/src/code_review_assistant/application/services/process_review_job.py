from datetime import timedelta
import asyncio
from code_review_assistant.application.ports.review_job_queue import ReviewJobQueue
from code_review_assistant.application.ports.review_result_writer import (
    ReviewResultWriter,
)
from code_review_assistant.application.services.review_pull_request import (
    ReviewPullRequest,
)

from code_review_assistant.application.models.claimed_review_job import ClaimedReviewJob

class ProcessReviewJob:
    def __init__(
        self,
        queue: ReviewJobQueue,
        review_pull_request: ReviewPullRequest,
        result_writer: ReviewResultWriter,
        lease_duration: timedelta = timedelta(minutes=5),
        retry_delay: timedelta = timedelta(minutes=1),
        max_attempts: int = 3,
    ) -> None:
        if lease_duration <= timedelta():
            raise ValueError("lease_duration must be positive")
        if retry_delay < timedelta():
            raise ValueError("retry_delay must not be negative")
        if (
            not isinstance(max_attempts, int)
            or isinstance(max_attempts, bool)
            or max_attempts < 1
        ):
            raise ValueError("max_attempts must be a positive integer")

        self._queue = queue
        self._review_pull_request = review_pull_request
        self._result_writer = result_writer
        self._lease_duration = lease_duration
        self._retry_delay = retry_delay
        self._max_attempts = max_attempts

    async def execute_once(self) -> bool:
        job = await self._queue.claim(
            self._lease_duration,
            self._max_attempts,
        )
        if job is None:
            return False

        try:
            async def review_and_save() -> None:
                result = await self._review_pull_request.execute(job.run)
                await self._result_writer.save(job, result)

            work_task = asyncio.create_task(review_and_save())
            heartbeat_task = asyncio.create_task(self._renew_lease(job))

            try:
                done, _ = await asyncio.wait(
                    (work_task, heartbeat_task),
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if work_task in done:
                    await work_task
                else:
                    await heartbeat_task
                    raise RuntimeError(
                        "review job lease heartbeat stopped unexpectedly"
                    )
            finally:
                for task in (work_task, heartbeat_task):
                    if not task.done():
                        task.cancel()

                await asyncio.gather(
                    work_task,
                    heartbeat_task,
                    return_exceptions=True,
                )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:2000]
            try:
                await self._queue.fail(
                    job,
                    error,
                    retry_delay=self._retry_delay,
                    max_attempts=self._max_attempts,
                )
            except Exception as fail_exc:
                raise exc from fail_exc
            raise

        return True

    async def _renew_lease(self, job: ClaimedReviewJob) -> None:
        interval = self._lease_duration.total_seconds() / 3

        while True:
            await asyncio.sleep(interval)
            await self._queue.renew(job, self._lease_duration)