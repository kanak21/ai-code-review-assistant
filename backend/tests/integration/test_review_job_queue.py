import asyncio
import os
from uuid import uuid4
from datetime import timedelta

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.infrastructure.database.engine import (
    create_database_engine,
    create_session_factory,
)
from code_review_assistant.infrastructure.database.review_job_queue import (
    SqlAlchemyReviewJobQueue,
)
from code_review_assistant.infrastructure.database.review_job_record import (
    ReviewJobRecord,
)
from code_review_assistant.settings import Settings


def test_review_job_queue_is_idempotent_and_rejects_delivery_reuse() -> None:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to run PostgreSQL integration tests")

    organization_id = f"review-job-test-{uuid4().hex}"
    settings = Settings().model_copy(update={"postgres_db": "review_assistant_test"})
    engine = create_database_engine(settings)
    session_factory: async_sessionmaker[AsyncSession] = create_session_factory(engine)

    run = ReviewRun(organization_id, "acme/service", 42, "revision-1")
    other_run = ReviewRun(organization_id, "acme/service", 42, "revision-2")
    delivery_id = f"delivery-{uuid4().hex}"

    async def verify_queue() -> None:
        try:
            queue = SqlAlchemyReviewJobQueue(session_factory)

            first_id = await queue.enqueue(run, delivery_id)
            assert await queue.enqueue(run, delivery_id) == first_id

            # Same review revision, but a distinct webhook delivery.
            assert await queue.enqueue(run, f"duplicate-{uuid4().hex}") == first_id

            with pytest.raises(ValueError, match="different review"):
                await queue.enqueue(other_run, delivery_id)

            async with session_factory() as session:
                records = (
                    await session.scalars(
                        select(ReviewJobRecord).where(
                            ReviewJobRecord.organization_id == organization_id
                        )
                    )
                ).all()

            assert len(records) == 1
            assert records[0].id == first_id
            assert records[0].status == "pending"
            assert records[0].attempt_count == 0
        finally:
            async with session_factory.begin() as session:
                await session.execute(
                    delete(ReviewJobRecord).where(
                        ReviewJobRecord.organization_id == organization_id
                    )
                )
            await engine.dispose()

    asyncio.run(
        verify_queue(),
        loop_factory=asyncio.SelectorEventLoop,
    )


def test_review_job_queue_claims_and_expires_leases() -> None:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to run PostgreSQL integration tests")

    organization_id = f"review-job-claim-{uuid4().hex}"
    settings = Settings().model_copy(update={"postgres_db": "review_assistant_test"})
    engine = create_database_engine(settings)
    session_factory: async_sessionmaker[AsyncSession] = create_session_factory(engine)
    run = ReviewRun(organization_id, "acme/service", 42, "revision-claim")

    async def verify_claims() -> None:
        try:
            queue = SqlAlchemyReviewJobQueue(session_factory)
            await queue.enqueue(run, f"delivery-{uuid4().hex}")

            first = await queue.claim(timedelta(minutes=1), max_attempts=2)
            assert first is not None
            assert first.run == run
            assert first.attempt_count == 1

            # An active lease prevents another worker from claiming this job.
            assert await queue.claim(timedelta(minutes=1), max_attempts=2) is None

            # Simulate lease expiry using the database clock.
            async with session_factory.begin() as session:
                await session.execute(
                    update(ReviewJobRecord)
                    .where(ReviewJobRecord.id == first.job_id)
                    .values(locked_until=text("now() - interval '1 minute'"))
                )

            second = await queue.claim(timedelta(minutes=1), max_attempts=2)
            assert second is not None
            assert second.job_id == first.job_id
            assert second.lease_token != first.lease_token
            assert second.attempt_count == 2

            # Expired jobs at the attempt limit become terminally failed.
            async with session_factory.begin() as session:
                await session.execute(
                    update(ReviewJobRecord)
                    .where(ReviewJobRecord.id == second.job_id)
                    .values(locked_until=text("now() - interval '1 minute'"))
                )

            assert await queue.claim(timedelta(minutes=1), max_attempts=2) is None

            async with session_factory() as session:
                record = await session.get(ReviewJobRecord, second.job_id)

            assert record is not None
            assert record.status == "failed"
            assert record.lease_token is None
        finally:
            async with session_factory.begin() as session:
                await session.execute(
                    delete(ReviewJobRecord).where(
                        ReviewJobRecord.organization_id == organization_id
                    )
                )
            await engine.dispose()

    asyncio.run(
        verify_claims(),
        loop_factory=asyncio.SelectorEventLoop,
    )


def test_concurrent_workers_claim_distinct_jobs() -> None:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to run PostgreSQL integration tests")

    organization_id = f"review-job-concurrent-{uuid4().hex}"
    settings = Settings().model_copy(update={"postgres_db": "review_assistant_test"})
    engine = create_database_engine(settings)
    session_factory: async_sessionmaker[AsyncSession] = create_session_factory(engine)

    runs = (
        ReviewRun(organization_id, "acme/service", 41, "revision-1"),
        ReviewRun(organization_id, "acme/service", 42, "revision-2"),
    )

    async def verify_concurrent_claims() -> None:
        try:
            queue = SqlAlchemyReviewJobQueue(session_factory)
            for run in runs:
                await queue.enqueue(run, f"delivery-{uuid4().hex}")

            claims = await asyncio.gather(
                queue.claim(timedelta(minutes=1), max_attempts=3),
                queue.claim(timedelta(minutes=1), max_attempts=3),
            )

            assert all(claim is not None for claim in claims)
            assert claims[0].job_id != claims[1].job_id
            assert {claim.run for claim in claims if claim is not None} == set(runs)
        finally:
            async with session_factory.begin() as session:
                await session.execute(
                    delete(ReviewJobRecord).where(
                        ReviewJobRecord.organization_id == organization_id
                    )
                )
            await engine.dispose()

    asyncio.run(
        verify_concurrent_claims(),
        loop_factory=asyncio.SelectorEventLoop,
    )


def test_complete_requires_current_unexpired_lease() -> None:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to run PostgreSQL integration tests")

    organization_id = f"review-job-complete-{uuid4().hex}"
    settings = Settings().model_copy(update={"postgres_db": "review_assistant_test"})
    engine = create_database_engine(settings)
    session_factory: async_sessionmaker[AsyncSession] = create_session_factory(engine)

    async def verify_completion() -> None:
        try:
            queue = SqlAlchemyReviewJobQueue(session_factory)
            run = ReviewRun(organization_id, "acme/service", 43, "revision-complete")
            await queue.enqueue(run, f"delivery-{uuid4().hex}")

            first_claim = await queue.claim(timedelta(minutes=1), max_attempts=3)
            assert first_claim is not None

            # Expire the first lease and let another worker claim the job.
            async with session_factory.begin() as session:
                await session.execute(
                    update(ReviewJobRecord)
                    .where(ReviewJobRecord.id == first_claim.job_id)
                    .values(locked_until=text("now() - interval '1 minute'"))
                )

            current_claim = await queue.claim(timedelta(minutes=1), max_attempts=3)
            assert current_claim is not None
            assert current_claim.lease_token != first_claim.lease_token

            with pytest.raises(RuntimeError, match="lease is no longer valid"):
                await queue.complete(first_claim)

            await queue.complete(current_claim)

            async with session_factory() as session:
                record = await session.get(ReviewJobRecord, current_claim.job_id)

            assert record is not None
            assert record.status == "completed"
            assert record.lease_token is None
            assert record.locked_until is None
        finally:
            async with session_factory.begin() as session:
                await session.execute(
                    delete(ReviewJobRecord).where(
                        ReviewJobRecord.organization_id == organization_id
                    )
                )
            await engine.dispose()

    asyncio.run(
        verify_completion(),
        loop_factory=asyncio.SelectorEventLoop,
    )


def test_fail_retries_then_marks_job_terminally_failed() -> None:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to run PostgreSQL integration tests")

    organization_id = f"review-job-fail-{uuid4().hex}"
    settings = Settings().model_copy(update={"postgres_db": "review_assistant_test"})
    engine = create_database_engine(settings)
    session_factory: async_sessionmaker[AsyncSession] = create_session_factory(engine)

    async def verify_failures() -> None:
        try:
            queue = SqlAlchemyReviewJobQueue(session_factory)
            run = ReviewRun(organization_id, "acme/service", 44, "revision-fail")
            await queue.enqueue(run, f"delivery-{uuid4().hex}")

            first = await queue.claim(timedelta(minutes=1), max_attempts=2)
            assert first is not None
            await queue.fail(
                first,
                "temporary test failure",
                retry_delay=timedelta(),
                max_attempts=2,
            )

            async with session_factory() as session:
                record = await session.get(ReviewJobRecord, first.job_id)
            assert record is not None
            assert record.status == "pending"
            assert record.last_error == "temporary test failure"
            assert record.lease_token is None
            assert record.locked_until is None

            second = await queue.claim(timedelta(minutes=1), max_attempts=2)
            assert second is not None
            assert second.attempt_count == 2

            await queue.fail(
                second,
                "retry limit reached",
                retry_delay=timedelta(),
                max_attempts=2,
            )

            async with session_factory() as session:
                record = await session.get(ReviewJobRecord, second.job_id)
            assert record is not None
            assert record.status == "failed"
            assert record.last_error == "retry limit reached"
            assert record.lease_token is None
            assert record.locked_until is None

            with pytest.raises(RuntimeError, match="lease is no longer valid"):
                await queue.fail(
                    second,
                    "stale worker",
                    retry_delay=timedelta(),
                    max_attempts=2,
                )
        finally:
            async with session_factory.begin() as session:
                await session.execute(
                    delete(ReviewJobRecord).where(
                        ReviewJobRecord.organization_id == organization_id
                    )
                )
            await engine.dispose()

    asyncio.run(
        verify_failures(),
        loop_factory=asyncio.SelectorEventLoop,
    )


def test_renew_extends_current_lease_and_rejects_stale_lease() -> None:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to run PostgreSQL integration tests")

    organization_id = f"review-job-renew-{uuid4().hex}"
    settings = Settings().model_copy(update={"postgres_db": "review_assistant_test"})
    engine = create_database_engine(settings)
    session_factory: async_sessionmaker[AsyncSession] = create_session_factory(engine)

    async def verify_renewal() -> None:
        try:
            queue = SqlAlchemyReviewJobQueue(session_factory)
            run = ReviewRun(organization_id, "acme/service", 45, "revision-renew")
            await queue.enqueue(run, f"delivery-{uuid4().hex}")

            original_claim = await queue.claim(timedelta(minutes=1), max_attempts=3)
            assert original_claim is not None

            # Expire the lease and let another worker take ownership.
            async with session_factory.begin() as session:
                await session.execute(
                    update(ReviewJobRecord)
                    .where(ReviewJobRecord.id == original_claim.job_id)
                    .values(locked_until=text("now() - interval '1 minute'"))
                )

            current_claim = await queue.claim(timedelta(minutes=1), max_attempts=3)
            assert current_claim is not None
            assert current_claim.lease_token != original_claim.lease_token

            with pytest.raises(RuntimeError, match="lease is no longer valid"):
                await queue.renew(original_claim, timedelta(minutes=5))

            async with session_factory() as session:
                original_deadline = await session.scalar(
                    select(ReviewJobRecord.locked_until).where(
                        ReviewJobRecord.id == current_claim.job_id
                    )
                )

            await queue.renew(current_claim, timedelta(minutes=5))

            async with session_factory() as session:
                renewed_deadline = await session.scalar(
                    select(ReviewJobRecord.locked_until).where(
                        ReviewJobRecord.id == current_claim.job_id
                    )
                )

            assert original_deadline is not None
            assert renewed_deadline is not None
            assert renewed_deadline > original_deadline
        finally:
            async with session_factory.begin() as session:
                await session.execute(
                    delete(ReviewJobRecord).where(
                        ReviewJobRecord.organization_id == organization_id
                    )
                )
            await engine.dispose()

    asyncio.run(
        verify_renewal(),
        loop_factory=asyncio.SelectorEventLoop,
    )