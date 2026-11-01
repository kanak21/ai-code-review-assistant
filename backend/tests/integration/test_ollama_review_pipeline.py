import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from code_review_assistant.application.services.index_standards import IndexStandards
from code_review_assistant.application.services.process_review_job import ProcessReviewJob
from code_review_assistant.application.services.retrieve_relevant_standards import (
    RetrieveRelevantStandards,
)
from code_review_assistant.application.services.review_pull_request import (
    ReviewPullRequest,
)
from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.review_finding import (
    ReviewFinding,
    Severity,
)
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.models.standard import Enforcement, Standard
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
from code_review_assistant.infrastructure.database.review_record import ReviewRecord
from code_review_assistant.infrastructure.database.review_result_writer import (
    SqlAlchemyReviewResultWriter,
)
from code_review_assistant.infrastructure.database.standard_embedding_store import (
    SqlAlchemyStandardEmbeddingStore,
)
from code_review_assistant.infrastructure.database.standard_record import StandardRecord
from code_review_assistant.infrastructure.database.standards_writer import (
    SqlAlchemyStandardsWriter,
)

from code_review_assistant.infrastructure.llm.ollama_text_embedder import (
    OllamaTextEmbedder,
)
from code_review_assistant.settings import Settings
from code_review_assistant.application.models.review_analysis import ReviewAnalysis
from code_review_assistant.infrastructure.database.review_finding_record import (
    ReviewFindingRecord,
)


@pytest.mark.integration
def test_ollama_review_is_persisted_through_job_processor() -> None:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to run PostgreSQL tests")
    if os.getenv("RUN_OLLAMA_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_OLLAMA_INTEGRATION_TESTS=1 to call local Ollama")

    organization_id = f"ollama-pipeline-{uuid4().hex}"
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    review_model = os.getenv("REVIEW_MODEL", "llama3.2:latest")
    embedding_model = os.getenv("EMBEDDING_MODEL", "nomic-embed-text:latest")
    dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))

    settings = Settings().model_copy(
        update={"postgres_db": "review_assistant_test"}
    )
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)

    run = ReviewRun(
        organization_id,
        "example/repository",
        1,
        f"revision-{uuid4().hex}",
    )
    changed_file = ChangedFile(
        path="src/Example.cs",
        kind=ChangeKind.MODIFIED,
        additions=1,
        deletions=1,
        patch="@@ -1 +1 @@\n-await task;\n+var value = task.Result;\n",
    )
    standard = Standard(
        standard_id=f"OLLAMA-{uuid4().hex[:12]}",
        version="1",
        title="Avoid blocking asynchronous code",
        guidance="Do not synchronously block on a Task.",
        source="ollama-pipeline-test",
        enforcement=Enforcement.MANDATORY,
        language="csharp",
        category="reliability",
        severity=Severity.HIGH,
    )

    class FakePullRequestReader:
        async def fetch_changed_files(
            self,
            requested_run: ReviewRun,
        ) -> tuple[ChangedFile, ...]:
            assert requested_run == run
            return (changed_file,)

    class FakeReviewAnalyzer:
        async def analyze(self, requested_run, changed_files, standards):
            return ReviewAnalysis(
                analyzed_paths=("src/Example.cs",),
                findings=(
                    ReviewFinding(
                        rule_id="TEST-001",
                        severity=Severity.HIGH,
                        title="Blocking asynchronous call",
                        rationale="This synchronously blocks on a task.",
                        file_path="src/Example.cs",
                        start_line=1,
                        end_line=1,
                        evidence="var value = task.Result;",
                        standard_id=standard.standard_id,
                    ),
                ),
                checks=(),
            )

    analyzer = FakeReviewAnalyzer()

    async def verify() -> None:
        try:
            await SqlAlchemyStandardsWriter(session_factory).add_many(
                organization_id,
                (standard,),
            )
            store = SqlAlchemyStandardEmbeddingStore(session_factory)

            async with httpx.AsyncClient(timeout=180.0) as client:
                embedder = OllamaTextEmbedder(
                    client,
                    base_url,
                    embedding_model,
                    dimensions,
                )
                assert await IndexStandards(store, embedder).execute(
                    organization_id
                ) == 1

                standards_reader = RetrieveRelevantStandards(store, embedder)
                workflow = ReviewPullRequest(
                    FakePullRequestReader(),
                    standards_reader,
                    analyzer,
                )

                queue = SqlAlchemyReviewJobQueue(session_factory)
                job_id = await queue.enqueue(run, f"delivery-{uuid4().hex}")
                processor = ProcessReviewJob(
                    queue,
                    workflow,
                    SqlAlchemyReviewResultWriter(session_factory),
                )

                assert await processor.execute_once() is True

            async with session_factory() as session:
                job = await session.get(ReviewJobRecord, job_id)
                review = await session.scalar(
                    select(ReviewRecord).where(ReviewRecord.job_id == job_id)
                )

            assert job is not None
            assert job.status == "completed"
            assert review is not None
            assert review.changed_files == 1
            assert review.analyzed_files == 1

            findings = []
            if review is not None:
                findings = (
                    await session.scalars(
                        select(ReviewFindingRecord).where(
                            ReviewFindingRecord.review_id == review.id
                        )
                    )
                ).all()

            assert len(findings) == 1
            assert findings[0].evidence == "var value = task.Result;"
        finally:
            async with session_factory.begin() as session:
                await session.execute(
                    delete(ReviewJobRecord).where(
                        ReviewJobRecord.organization_id == organization_id
                    )
                )
                await session.execute(
                    delete(StandardRecord).where(
                        StandardRecord.organization_id == organization_id
                    )
                )
            await engine.dispose()

    asyncio.run(verify(), loop_factory=asyncio.SelectorEventLoop)