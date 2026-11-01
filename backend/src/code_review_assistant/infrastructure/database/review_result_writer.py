from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from code_review_assistant.application.models.claimed_review_job import (
    ClaimedReviewJob,
)
from code_review_assistant.application.ports.review_result_writer import (
    ReviewResultWriter,
)
from code_review_assistant.domain.models.review_result import ReviewResult
from code_review_assistant.infrastructure.database.review_check_record import (
    ReviewCheckRecord,
)
from code_review_assistant.infrastructure.database.review_finding_record import (
    ReviewFindingRecord,
)
from code_review_assistant.infrastructure.database.review_job_record import (
    ReviewJobRecord,
)
from code_review_assistant.infrastructure.database.review_record import ReviewRecord


class SqlAlchemyReviewResultWriter(ReviewResultWriter):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def save(self, job: ClaimedReviewJob, result: ReviewResult) -> UUID:
        if not isinstance(job, ClaimedReviewJob):
            raise ValueError("job must be a ClaimedReviewJob")
        if not isinstance(result, ReviewResult):
            raise ValueError("result must be a ReviewResult")
        if result.run != job.run:
            raise ValueError("review result run must match claimed job")

        async with self._session_factory.begin() as session:
            job_record = await session.scalar(
                select(ReviewJobRecord)
                .where(
                    ReviewJobRecord.id == job.job_id,
                    ReviewJobRecord.status == "processing",
                    ReviewJobRecord.lease_token == job.lease_token,
                    ReviewJobRecord.locked_until > func.clock_timestamp(),
                    ReviewJobRecord.organization_id == job.run.organization_id,
                    ReviewJobRecord.repository_id == job.run.repository_id,
                    ReviewJobRecord.pull_request_number == job.run.pull_request_number,
                    ReviewJobRecord.revision == job.run.revision,
                )
                .with_for_update()
            )
            if job_record is None:
                raise RuntimeError("review job lease is no longer valid")

            existing = await session.scalar(
                select(ReviewRecord).where(ReviewRecord.job_id == job.job_id)
            )

            if existing is None:
                review = ReviewRecord(
                    job_id=job.job_id,
                    changed_files=result.coverage.changed_files,
                    analyzed_files=result.coverage.analyzed_files,
                )
                session.add(review)
                await session.flush()

                session.add_all(
                    [
                        ReviewFindingRecord(
                            review_id=review.id,
                            rule_id=finding.rule_id,
                            standard_id=finding.standard_id,
                            severity=finding.severity.value,
                            title=finding.title,
                            rationale=finding.rationale,
                            file_path=finding.file_path,
                            start_line=finding.start_line,
                            end_line=finding.end_line,
                            evidence=finding.evidence,
                        )
                        for finding in result.findings
                    ]
                )
                session.add_all(
                    [
                        ReviewCheckRecord(
                            review_id=review.id,
                            check_id=check.check_id,
                            status=check.status.value,
                            summary=check.summary,
                        )
                        for check in result.checks
                    ]
                )
                review_id = review.id
            else:
                review_id = existing.id

            job_record.status = "completed"
            job_record.locked_until = None
            job_record.lease_token = None
            job_record.last_error = None

            return review_id