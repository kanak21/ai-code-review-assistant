import asyncio

import pytest

from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.review_finding import Severity
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.models.standard import Enforcement, Standard
from code_review_assistant.infrastructure.analysis.csharp_standards_analyzer import (
    CSharpStandardsAnalyzer,
)


def make_blocking_async_standard() -> Standard:
    return Standard(
        standard_id="DEMO-CS-02",
        version="1",
        title="Avoid blocking asynchronous code",
        guidance="Do not use .Result or .Wait() to synchronously block on a Task.",
        source="Fictional demo standards",
        enforcement=Enforcement.MANDATORY,
        language="csharp",
        category="reliability",
        severity=Severity.HIGH,
    )


@pytest.mark.parametrize(
    "added_line",
    [
        "var value = task.Result;",
        "task.Wait();",
    ],
)
def test_reports_blocking_async_call_on_added_line(added_line: str) -> None:
    old_line = "await task;"
    changed_file = ChangedFile(
        path="src/Example.cs",
        kind=ChangeKind.MODIFIED,
        additions=1,
        deletions=1,
        patch=f"@@ -1,1 +1,1 @@\n-{old_line}\n+{added_line}\n",
    )
    analyzer = CSharpStandardsAnalyzer()

    analysis = asyncio.run(
        analyzer.analyze(
            ReviewRun("demo-org", "demo-repo", 1, "revision-1"),
            (changed_file,),
            (make_blocking_async_standard(),),
        )
    )

    assert analysis.analyzed_paths == ("src/Example.cs",)
    assert len(analysis.findings) == 1
    finding = analysis.findings[0]
    assert finding.standard_id == "DEMO-CS-02"
    assert finding.file_path == "src/Example.cs"
    assert finding.start_line == 1
    assert finding.end_line == 1
    assert finding.evidence == added_line


def test_does_not_report_clean_changed_line() -> None:
    changed_file = ChangedFile(
        path="src/Example.cs",
        kind=ChangeKind.MODIFIED,
        additions=1,
        deletions=1,
        patch="@@ -1,1 +1,1 @@\n-await task;\n+await task.ConfigureAwait(false);\n",
    )
    analyzer = CSharpStandardsAnalyzer()

    analysis = asyncio.run(
        analyzer.analyze(
            ReviewRun("demo-org", "demo-repo", 1, "revision-1"),
            (changed_file,),
            (make_blocking_async_standard(),),
        )
    )

    assert analysis.analyzed_paths == ("src/Example.cs",)
    assert analysis.findings == ()


def test_does_not_report_rule_when_standard_is_not_supplied() -> None:
    changed_file = ChangedFile(
        path="src/Example.cs",
        kind=ChangeKind.MODIFIED,
        additions=1,
        deletions=1,
        patch="@@ -1,1 +1,1 @@\n-await task;\n+var value = task.Result;\n",
    )
    analyzer = CSharpStandardsAnalyzer()

    analysis = asyncio.run(
        analyzer.analyze(
            ReviewRun("demo-org", "demo-repo", 1, "revision-1"),
            (changed_file,),
            (),
        )
    )

    assert analysis.analyzed_paths == ("src/Example.cs",)
    assert analysis.findings == ()