from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, cast, func, or_, select, update, Interval
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from code_review_assistant.application.ports.review_job_queue import ReviewJobQueue
from code_review_assistant.application.models.claimed_review_job import (
    ClaimedReviewJob,
)
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.infrastructure.database.review_job_record import (
    ReviewJobRecord,
)


class SqlAlchemyReviewJobQueue(ReviewJobQueue):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def enqueue(
        self,
        run: ReviewRun,
        github_delivery_id: str,
    ) -> UUID:
        if not isinstance(run, ReviewRun):
            raise ValueError("run must be a ReviewRun")
        if (
            not isinstance(github_delivery_id, str)
            or not github_delivery_id.strip()
            or len(github_delivery_id) > 255
        ):
            raise ValueError("github_delivery_id must be 1-255 characters")

        statement = (
            insert(ReviewJobRecord)
            .values(
                organization_id=run.organization_id,
                repository_id=run.repository_id,
                pull_request_number=run.pull_request_number,
                revision=run.revision,
                github_delivery_id=github_delivery_id,
            )
            .on_conflict_do_nothing()
            .returning(ReviewJobRecord.id)
        )

        async with self._session_factory.begin() as session:
            job_id = await session.scalar(statement)
            if job_id is not None:
                return job_id

            existing_delivery = await session.scalar(
                select(ReviewJobRecord).where(
                    ReviewJobRecord.github_delivery_id == github_delivery_id
                )
            )
            if existing_delivery is not None:
                if not self._matches_run(existing_delivery, run):
                    raise ValueError(
                        "GitHub delivery ID is already associated with a different review"
                    )
                return existing_delivery.id

            existing_revision = await session.scalar(
                select(ReviewJobRecord).where(
                    ReviewJobRecord.organization_id == run.organization_id,
                    ReviewJobRecord.repository_id == run.repository_id,
                    ReviewJobRecord.pull_request_number == run.pull_request_number,
                    ReviewJobRecord.revision == run.revision,
                )
            )
            if existing_revision is not None:
                return existing_revision.id

            raise RuntimeError("Review job insert conflicted but no existing job was found")

    @staticmethod
    def _matches_run(record: ReviewJobRecord, run: ReviewRun) -> bool:
        return (
            record.organization_id == run.organization_id
            and record.repository_id == run.repository_id
            and record.pull_request_number == run.pull_request_number
            and record.revision == run.revision
        )

    async def claim(
        self,
        lease_duration: timedelta,
        max_attempts: int,
    ) -> ClaimedReviewJob | None:
        if not isinstance(lease_duration, timedelta) or lease_duration <= timedelta():
            raise ValueError("lease_duration must be positive")
        if (
            not isinstance(max_attempts, int)
            or isinstance(max_attempts, bool)
            or max_attempts < 1
        ):
            raise ValueError("max_attempts must be a positive integer")

        ready = or_(
            and_(
                ReviewJobRecord.status == "pending",
                ReviewJobRecord.available_at <= func.now(),
            ),
            and_(
                ReviewJobRecord.status == "processing",
                or_(
                    ReviewJobRecord.locked_until.is_(None),
                    ReviewJobRecord.locked_until <= func.now(),
                ),
            ),
        )

        async with self._session_factory.begin() as session:
            await session.execute(
                update(ReviewJobRecord)
                .where(ready, ReviewJobRecord.attempt_count >= max_attempts)
                .values(
                    status="failed",
                    locked_until=None,
                    lease_token=None,
                    last_error="Maximum claim attempts reached.",
                    updated_at=func.now(),
                )
            )

            record = await session.scalar(
                select(ReviewJobRecord)
                .where(ready, ReviewJobRecord.attempt_count < max_attempts)
                .order_by(ReviewJobRecord.available_at, ReviewJobRecord.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if record is None:
                return None

            lease_token = uuid4()
            attempt_count = record.attempt_count + 1

            await session.execute(
                update(ReviewJobRecord)
                .where(ReviewJobRecord.id == record.id)
                .values(
                    status="processing",
                    attempt_count=attempt_count,
                    lease_token=lease_token,
                    locked_until=func.now() + cast(lease_duration, Interval),
                    last_error=None,
                    updated_at=func.now(),
                )
            )

            return ClaimedReviewJob(
                job_id=record.id,
                run=ReviewRun(
                    organization_id=record.organization_id,
                    repository_id=record.repository_id,
                    pull_request_number=record.pull_request_number,
                    revision=record.revision,
                ),
                lease_token=lease_token,
                attempt_count=attempt_count,
            )

    async def complete(self, job: ClaimedReviewJob) -> None:
        if not isinstance(job, ClaimedReviewJob):
            raise ValueError("job must be a ClaimedReviewJob")

        statement = (
            update(ReviewJobRecord)
            .where(
                ReviewJobRecord.id == job.job_id,
                ReviewJobRecord.status == "processing",
                ReviewJobRecord.lease_token == job.lease_token,
                ReviewJobRecord.locked_until > func.now(),
            )
            .values(
                status="completed",
                locked_until=None,
                lease_token=None,
                last_error=None,
                updated_at=func.now(),
            )
            .returning(ReviewJobRecord.id)
        )

        async with self._session_factory.begin() as session:
            completed_id = await session.scalar(statement)

        if completed_id is None:
            raise RuntimeError("review job lease is no longer valid")

    async def fail(
        self,
        job: ClaimedReviewJob,
        error: str,
        retry_delay: timedelta,
        max_attempts: int,
    ) -> None:
        if not isinstance(job, ClaimedReviewJob):
            raise ValueError("job must be a ClaimedReviewJob")
        if not isinstance(error, str) or not error.strip() or len(error) > 2000:
            raise ValueError("error must be 1-2000 non-whitespace characters")
        if not isinstance(retry_delay, timedelta) or retry_delay < timedelta():
            raise ValueError("retry_delay must not be negative")
        if (
            not isinstance(max_attempts, int)
            or isinstance(max_attempts, bool)
            or max_attempts < 1
        ):
            raise ValueError("max_attempts must be a positive integer")

        terminal = job.attempt_count >= max_attempts
        statement = (
            update(ReviewJobRecord)
            .where(
                ReviewJobRecord.id == job.job_id,
                ReviewJobRecord.status == "processing",
                ReviewJobRecord.lease_token == job.lease_token,
                ReviewJobRecord.locked_until > func.now(),
            )
            .values(
                status="failed" if terminal else "pending",
                available_at=func.now() + cast(retry_delay, Interval),
                locked_until=None,
                lease_token=None,
                last_error=error,
                updated_at=func.now(),
            )
            .returning(ReviewJobRecord.id)
        )

        async with self._session_factory.begin() as session:
            failed_id = await session.scalar(statement)

        if failed_id is None:
            raise RuntimeError("review job lease is no longer valid")

    async def renew(
        self,
        job: ClaimedReviewJob,
        lease_duration: timedelta,
    ) -> None:
        if not isinstance(job, ClaimedReviewJob):
            raise ValueError("job must be a ClaimedReviewJob")
        if not isinstance(lease_duration, timedelta) or lease_duration <= timedelta():
            raise ValueError("lease_duration must be positive")

        statement = (
            update(ReviewJobRecord)
            .where(
                ReviewJobRecord.id == job.job_id,
                ReviewJobRecord.status == "processing",
                ReviewJobRecord.lease_token == job.lease_token,
                ReviewJobRecord.locked_until > func.clock_timestamp(),
            )
            .values(
                locked_until=func.clock_timestamp() + cast(lease_duration, Interval),
                updated_at=func.clock_timestamp(),
            )
            .returning(ReviewJobRecord.id)
        )

        async with self._session_factory.begin() as session:
            renewed_id = await session.scalar(statement)

        if renewed_id is None:
            raise RuntimeError("review job lease is no longer valid")