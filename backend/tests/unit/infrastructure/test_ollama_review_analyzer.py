import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.review_finding import Severity
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.models.standard import Enforcement, Standard
from code_review_assistant.infrastructure.llm.ollama_review_analyzer import (
    OllamaReviewAnalyzer,
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


class FakeResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, object]:
        return {"message": {"content": self._content}}


def make_analyzer(content: str):
    post = AsyncMock(return_value=FakeResponse(content))
    client = SimpleNamespace(post=post)
    analyzer = OllamaReviewAnalyzer(
        client,
        "http://127.0.0.1:11434/",
        "llama3.2:latest",
    )
    return analyzer, post


def test_ollama_analyzer_parses_and_validates_review() -> None:
    content = json.dumps({"findings": [make_finding()]})
    analyzer, post = make_analyzer(content)

    result = asyncio.run(
        analyzer.analyze(
            ReviewRun("org-1", "repo-1", 1, "revision-1"),
            (make_file(),),
            (make_standard(),),
        )
    )

    assert result.analyzed_paths == ("src/Example.cs",)
    assert len(result.findings) == 1
    assert result.findings[0].evidence == "var value = task.Result;"
    assert post.await_args.args[0] == "http://127.0.0.1:11434/api/chat"
    assert post.await_args.kwargs["json"]["model"] == "llama3.2:latest"
    assert post.await_args.kwargs["json"]["stream"] is False


def test_ollama_analyzer_rejects_malformed_json() -> None:
    analyzer, _ = make_analyzer("{not-json")

    with pytest.raises(RuntimeError, match="malformed review JSON"):
        asyncio.run(
            analyzer.analyze(
                ReviewRun("org-1", "repo-1", 1, "revision-1"),
                (make_file(),),
                (make_standard(),),
            )
        )


def test_ollama_analyzer_rejects_unverified_evidence() -> None:
    content = json.dumps(
        {"findings": [make_finding(evidence="invented evidence")]}
    )
    analyzer, _ = make_analyzer(content)

    with pytest.raises(ValueError, match="evidence must exactly match"):
        asyncio.run(
            analyzer.analyze(
                ReviewRun("org-1", "repo-1", 1, "revision-1"),
                (make_file(),),
                (make_standard(),),
            )
        )