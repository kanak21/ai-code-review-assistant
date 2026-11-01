import asyncio
import os

import httpx
import pytest

from code_review_assistant.application.models.review_analysis import ReviewAnalysis
from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.review_finding import Severity
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.models.standard import Enforcement, Standard
from code_review_assistant.infrastructure.llm.ollama_review_analyzer import (
    OllamaReviewAnalyzer,
)


@pytest.mark.integration
def test_ollama_reviews_csharp_diff_with_local_model() -> None:
    if os.getenv("RUN_OLLAMA_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_OLLAMA_INTEGRATION_TESTS=1 to call local Ollama")

    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    model = os.getenv("REVIEW_MODEL", "llama3.2:latest")

    run = ReviewRun(
        organization_id="local-test",
        repository_id="example/repository",
        pull_request_number=1,
        revision="local-test-revision",
    )
    changed_file = ChangedFile(
        path="src/Example.cs",
        kind=ChangeKind.MODIFIED,
        additions=1,
        deletions=1,
        patch=(
            "@@ -1 +1 @@\n"
            "-await task;\n"
            "+var value = task.Result;\n"
        ),
    )
    standard = Standard(
        standard_id="ORG-CS-02",
        version="1",
        title="Avoid blocking asynchronous code",
        guidance="Do not synchronously block on a Task.",
        source="local-integration-test",
        enforcement=Enforcement.MANDATORY,
        language="csharp",
        category="reliability",
        severity=Severity.HIGH,
    )

    async def review() -> ReviewAnalysis:
        async with httpx.AsyncClient(timeout=180.0) as client:
            analyzer = OllamaReviewAnalyzer(client, base_url, model)
            return await analyzer.analyze(run, (changed_file,), (standard,))

    result = asyncio.run(review())

    assert isinstance(result, ReviewAnalysis)
    assert result.analyzed_paths == ("src/Example.cs",)

    for finding in result.findings:
        assert finding.standard_id == standard.standard_id
        assert finding.file_path == changed_file.path
        assert finding.evidence == "var value = task.Result;"
        assert finding.start_line == finding.end_line == 1