import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.review_finding import Severity
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.models.standard import Enforcement, Standard
from code_review_assistant.infrastructure.llm.anthropic_review_analyzer import (
    AnthropicReviewAnalyzer,
)


def make_standard() -> Standard:
    return Standard(
        standard_id="ORG-CS-02",
        version="1",
        title="Avoid blocking asynchronous code",
        guidance="Do not synchronously block on a Task.",
        source="engineering/csharp.md",
        enforcement=Enforcement.MANDATORY,
        language="csharp",
        category="reliability",
        severity=Severity.HIGH,
    )


def make_response(finding: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use",
                name="submit_review",
                input={"findings": [finding]},
            )
        ]
    )


def make_finding(**overrides: object) -> dict[str, object]:
    finding: dict[str, object] = {
        "rule_id": "AI-001",
        "standard_id": "ORG-CS-02",
        "severity": "high",
        "title": "Blocking async call",
        "rationale": "This blocks synchronously on an asynchronous task.",
        "file_path": "src/Example.cs",
        "start_line": 1,
        "end_line": 1,
        "evidence": "var value = task.Result;",
    }
    finding.update(overrides)
    return finding


def make_file() -> ChangedFile:
    return ChangedFile(
        path="src/Example.cs",
        kind=ChangeKind.MODIFIED,
        additions=1,
        deletions=1,
        patch="@@ -1 +1 @@\n-await task;\n+var value = task.Result;\n",
    )


def make_analyzer(finding: dict[str, object]):
    create = AsyncMock(return_value=make_response(finding))
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    return AnthropicReviewAnalyzer(client, model="test-model"), create


def test_analyzer_maps_structured_response_to_valid_finding() -> None:
    analyzer, create = make_analyzer(make_finding())

    result = asyncio.run(
        analyzer.analyze(
            ReviewRun("org-1", "repo-1", 1, "revision-1"),
            (make_file(),),
            (make_standard(),),
        )
    )

    assert result.analyzed_paths == ("src/Example.cs",)
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.standard_id == "ORG-CS-02"
    assert finding.severity is Severity.HIGH
    assert finding.file_path == "src/Example.cs"
    assert finding.start_line == finding.end_line == 1
    assert finding.evidence == "var value = task.Result;"
    assert create.await_args.kwargs["model"] == "test-model"


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"standard_id": "UNSUPPLIED-RULE"},
        {"evidence": "This text is not in the diff."},
        {"start_line": 99, "end_line": 99},
    ],
)
def test_analyzer_rejects_untrusted_or_invalid_findings(
    invalid_fields: dict[str, object],
) -> None:
    analyzer, _ = make_analyzer(make_finding(**invalid_fields))

    with pytest.raises((ValueError, RuntimeError)):
        asyncio.run(
            analyzer.analyze(
                ReviewRun("org-1", "repo-1", 1, "revision-1"),
                (make_file(),),
                (make_standard(),),
            )
        )