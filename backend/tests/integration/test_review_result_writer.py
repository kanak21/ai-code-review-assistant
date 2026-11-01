import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.check_result import CheckResult, CheckStatus
from code_review_assistant.domain.models.review_coverage import ReviewCoverage
from code_review_assistant.domain.models.review_finding import ReviewFinding, Severity
from code_review_assistant.domain.models.review_result import ReviewResult
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.infrastructure.database.engine import (
    create_database_engine,
    create_session_factory,
)
from code_review_assistant.infrastructure.database.review_check_record import (
    ReviewCheckRecord,
)
from code_review_assistant.infrastructure.database.review_finding_record import (
    ReviewFindingRecord,
)
from code_review_assistant.infrastructure.database.review_job_queue import (
    SqlAlchemyReviewJobQueue,
)
from code_review_assistant.infrastructure.database.review_job_record import (
    ReviewJobRecord,
)
from code_review_assistant.infrastructure.database.review_record import ReviewRecord
from code_review_assistant.infrastructure.database.review_result_writer import (
    SqlAlchemyReviewResultWriter,
)
from code_review_assistant.settings import Settings
from code_review_assistant.application.services.process_review_job import ProcessReviewJob


def test_result_save_persists_and_completes_only_with_current_lease() -> None:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to run PostgreSQL integration tests")

    organization_id = f"review-result-test-{uuid4().hex}"
    settings = Settings().model_copy(update={"postgres_db": "review_assistant_test"})
    engine = create_database_engine(settings)
    session_factory: async_sessionmaker[AsyncSession] = create_session_factory(engine)

    run = ReviewRun(organization_id, "acme/service", 42, "revision-1")
    changed_file = ChangedFile(
        path="src/example.cs",
        kind=ChangeKind.MODIFIED,
        additions=1,
        deletions=0,
        patch="@@ -0,0 +1 @@\n+var value = 1;\n",
    )
    result = ReviewResult(
        run=run,
        changed_files=(changed_file,),
        findings=(
            ReviewFinding(
                rule_id="TEST-001",
                severity=Severity.MEDIUM,
                title="Example finding",
                rationale="Test rationale.",
                file_path="src/example.cs",
                start_line=1,
                end_line=1,
                evidence="var value = 1;",
                standard_id="ORG-CS-01",
            ),
        ),
        checks=(CheckResult("tests", CheckStatus.NOT_RUN, "Not run"),),
        coverage=ReviewCoverage(changed_files=1, analyzed_files=1),
    )

    async def verify() -> None:
        try:
            queue = SqlAlchemyReviewJobQueue(session_factory)
            writer = SqlAlchemyReviewResultWriter(session_factory)

            await queue.enqueue(run, f"delivery-{uuid4().hex}")
            stale_claim = await queue.claim(timedelta(minutes=1), max_attempts=3)
            assert stale_claim is not None

            async with session_factory.begin() as session:
                await session.execute(
                    update(ReviewJobRecord)
                    .where(ReviewJobRecord.id == stale_claim.job_id)
                    .values(locked_until=text("now() - interval '1 minute'"))
                )

            current_claim = await queue.claim(timedelta(minutes=1), max_attempts=3)
            assert current_claim is not None
            assert current_claim.lease_token != stale_claim.lease_token

            with pytest.raises(RuntimeError, match="lease is no longer valid"):
                await writer.save(stale_claim, result)

            async with session_factory() as session:
                assert await session.scalar(select(ReviewRecord.id)) is None

            await writer.save(current_claim, result)

            async with session_factory() as session:
                review = await session.scalar(
                    select(ReviewRecord).where(ReviewRecord.job_id == current_claim.job_id)
                )
                assert review is not None
                assert review.changed_files == 1
                assert review.analyzed_files == 1

                findings = (
                    await session.scalars(
                        select(ReviewFindingRecord).where(
                            ReviewFindingRecord.review_id == review.id
                        )
                    )
                ).all()
                checks = (
                    await session.scalars(
                        select(ReviewCheckRecord).where(
                            ReviewCheckRecord.review_id == review.id
                        )
                    )
                ).all()
                job = await session.get(ReviewJobRecord, current_claim.job_id)

            assert len(findings) == 1
            assert findings[0].evidence == "var value = 1;"
            assert len(checks) == 1
            assert checks[0].status == "not_run"
            assert job is not None
            assert job.status == "completed"
            assert job.lease_token is None
        finally:
            async with session_factory.begin() as session:
                await session.execute(
                    delete(ReviewJobRecord).where(
                        ReviewJobRecord.organization_id == organization_id
                    )
                )
            await engine.dispose()

    asyncio.run(verify(), loop_factory=asyncio.SelectorEventLoop)


def test_processor_claims_reviews_and_persists_result() -> None:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to run PostgreSQL integration tests")

    organization_id = f"processor-test-{uuid4().hex}"
    settings = Settings().model_copy(update={"postgres_db": "review_assistant_test"})
    engine = create_database_engine(settings)
    session_factory: async_sessionmaker[AsyncSession] = create_session_factory(engine)

    run = ReviewRun(organization_id, "acme/service", 45, "revision-processor")
    result = ReviewResult(
        run=run,
        changed_files=(),
        findings=(),
        checks=(CheckResult("tests", CheckStatus.NOT_RUN, "Not run"),),
        coverage=ReviewCoverage(changed_files=0, analyzed_files=0),
    )

    class FakeReviewWorkflow:
        async def execute(self, requested_run: ReviewRun) -> ReviewResult:
            assert requested_run == run
            return result

    async def verify() -> None:
        try:
            queue = SqlAlchemyReviewJobQueue(session_factory)
            writer = SqlAlchemyReviewResultWriter(session_factory)
            job_id = await queue.enqueue(run, f"delivery-{uuid4().hex}")

            processor = ProcessReviewJob(queue, FakeReviewWorkflow(), writer)
            assert await processor.execute_once() is True
            assert await processor.execute_once() is False

            async with session_factory() as session:
                job = await session.get(ReviewJobRecord, job_id)
                review = await session.scalar(
                    select(ReviewRecord).where(ReviewRecord.job_id == job_id)
                )

                assert job is not None
                assert job.status == "completed"
                assert review is not None
                checks = (
                    await session.scalars(
                        select(ReviewCheckRecord).where(
                            ReviewCheckRecord.review_id == review.id
                        )
                    )
                ).all()

            assert len(checks) == 1
            assert checks[0].check_id == "tests"
            assert checks[0].status == "not_run"
        finally:
            async with session_factory.begin() as session:
                await session.execute(
                    delete(ReviewJobRecord).where(
                        ReviewJobRecord.organization_id == organization_id
                    )
                )
            await engine.dispose()

    asyncio.run(verify(), loop_factory=asyncio.SelectorEventLoop)