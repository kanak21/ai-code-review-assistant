import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest

from code_review_assistant.application.models.claimed_review_job import (
    ClaimedReviewJob,
)
from code_review_assistant.application.services.process_review_job import (
    ProcessReviewJob,
)
from code_review_assistant.domain.models.review_coverage import ReviewCoverage
from code_review_assistant.domain.models.review_result import ReviewResult
from code_review_assistant.domain.models.review_run import ReviewRun


class FakeQueue:
    def __init__(
        self,
        job: ClaimedReviewJob | None,
        fail_error: Exception | None = None,
    ) -> None:
        self.job = job
        self.fail_error = fail_error
        self.claim_args: tuple[timedelta, int] | None = None
        self.fail_args: tuple[object, str, timedelta, int] | None = None
        self.renew_calls: list[tuple[ClaimedReviewJob, timedelta]] = []
        self.renewed = asyncio.Event()

    async def claim(
        self,
        lease_duration: timedelta,
        max_attempts: int,
    ) -> ClaimedReviewJob | None:
        self.claim_args = (lease_duration, max_attempts)
        return self.job

    async def fail(
        self,
        job: ClaimedReviewJob,
        error: str,
        retry_delay: timedelta,
        max_attempts: int,
    ) -> None:
        self.fail_args = (job, error, retry_delay, max_attempts)
        if self.fail_error is not None:
            raise self.fail_error

    async def renew(
        self,
        job: ClaimedReviewJob,
        lease_duration: timedelta,
    ) -> None:
        self.renew_calls.append((job, lease_duration))
        self.renewed.set()


class FakeReviewWorkflow:
    def __init__(
        self,
        result: ReviewResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.received_run: ReviewRun | None = None

    async def execute(self, run: ReviewRun) -> ReviewResult:
        self.received_run = run
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


class FakeResultWriter:
    def __init__(self) -> None:
        self.saved: tuple[ClaimedReviewJob, ReviewResult] | None = None

    async def save(self, job: ClaimedReviewJob, result: ReviewResult):
        self.saved = (job, result)
        return uuid4()


def make_job() -> ClaimedReviewJob:
    return ClaimedReviewJob(
        job_id=uuid4(),
        run=ReviewRun("org-1", "acme/service", 42, "revision-1"),
        lease_token=uuid4(),
        attempt_count=1,
    )


def make_result(run: ReviewRun) -> ReviewResult:
    return ReviewResult(
        run=run,
        changed_files=(),
        findings=(),
        checks=(),
        coverage=ReviewCoverage(changed_files=0, analyzed_files=0),
    )


def test_execute_once_returns_false_when_queue_is_empty() -> None:
    queue = FakeQueue(None)
    workflow = FakeReviewWorkflow()
    writer = FakeResultWriter()
    processor = ProcessReviewJob(queue, workflow, writer)

    assert asyncio.run(processor.execute_once()) is False
    assert queue.claim_args == (timedelta(minutes=5), 3)
    assert workflow.received_run is None
    assert writer.saved is None


def test_execute_once_reviews_and_saves_claimed_job() -> None:
    job = make_job()
    result = make_result(job.run)
    queue = FakeQueue(job)
    workflow = FakeReviewWorkflow(result=result)
    writer = FakeResultWriter()
    processor = ProcessReviewJob(queue, workflow, writer)

    assert asyncio.run(processor.execute_once()) is True
    assert workflow.received_run == job.run
    assert writer.saved == (job, result)
    assert queue.fail_args is None


def test_execute_once_records_failure_and_reraises() -> None:
    job = make_job()
    error = RuntimeError("provider unavailable")
    queue = FakeQueue(job)
    workflow = FakeReviewWorkflow(error=error)
    writer = FakeResultWriter()
    processor = ProcessReviewJob(
        queue,
        workflow,
        writer,
        retry_delay=timedelta(seconds=30),
        max_attempts=4,
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        asyncio.run(processor.execute_once())

    assert queue.fail_args == (
        job,
        "RuntimeError: provider unavailable",
        timedelta(seconds=30),
        4,
    )
    assert writer.saved is None


def test_execute_once_renews_lease_during_review() -> None:
    job = make_job()
    result = make_result(job.run)
    queue = FakeQueue(job)
    workflow = BlockingReviewWorkflow(result)
    writer = FakeResultWriter()
    lease_duration = timedelta(milliseconds=300)
    processor = ProcessReviewJob(
        queue,
        workflow,
        writer,
        lease_duration=lease_duration,
    )

    async def verify_renewal() -> None:
        task = asyncio.create_task(processor.execute_once())
        try:
            await workflow.started.wait()
            await queue.renewed.wait()
        finally:
            workflow.release.set()

        assert await task is True

    asyncio.run(verify_renewal())

    assert queue.renew_calls
    assert queue.renew_calls[0] == (job, lease_duration)
    assert writer.saved == (job, result)
    assert queue.fail_args is None


class BlockingReviewWorkflow:
    def __init__(self, result: ReviewResult) -> None:
        self.result = result
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(self, run: ReviewRun) -> ReviewResult:
        self.started.set()
        await self.release.wait()
        return self.result


def test_execute_once_preserves_workflow_error_when_recording_failure_fails() -> None:
    job = make_job()
    workflow_error = RuntimeError("provider unavailable")
    lease_error = RuntimeError("lease is no longer valid")
    queue = FakeQueue(job, fail_error=lease_error)
    workflow = FakeReviewWorkflow(error=workflow_error)
    processor = ProcessReviewJob(queue, workflow, FakeResultWriter())

    with pytest.raises(RuntimeError, match="provider unavailable") as exc_info:
        asyncio.run(processor.execute_once())

    assert exc_info.value is workflow_error
    assert exc_info.value.__cause__ is lease_error