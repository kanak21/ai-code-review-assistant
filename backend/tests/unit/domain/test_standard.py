import pytest

from code_review_assistant.domain.models.review_finding import Severity
from code_review_assistant.domain.models.standard import Enforcement, Standard


def make_standard(
    *,
    category: str = "reliability",
    severity: Severity = Severity.MEDIUM,
) -> Standard:
    return Standard(
        standard_id="ORG-CSharp-01",
        version="2026-01",
        title="Use cancellation tokens",
        guidance="Pass cancellation tokens through asynchronous calls.",
        source="engineering/async-guidance.md",
        enforcement=Enforcement.MANDATORY,
        language="csharp",
        category=category,
        severity=severity,
    )


def test_standard_preserves_version_provenance_category_and_severity() -> None:
    standard = make_standard()

    assert standard.version == "2026-01"
    assert standard.source == "engineering/async-guidance.md"
    assert standard.category == "reliability"
    assert standard.severity is Severity.MEDIUM


def test_standard_rejects_empty_guidance() -> None:
    with pytest.raises(ValueError, match="guidance"):
        Standard(
            standard_id="ORG-CSharp-01",
            version="2026-01",
            title="Use cancellation tokens",
            guidance=" ",
            source="engineering/async-guidance.md",
            enforcement=Enforcement.MANDATORY,
            language="csharp",
            category="reliability",
            severity=Severity.MEDIUM,
        )


def test_standard_rejects_empty_category() -> None:
    with pytest.raises(ValueError, match="category"):
        make_standard(category=" ")


def test_standard_rejects_invalid_severity() -> None:
    with pytest.raises(ValueError, match="severity"):
        make_standard(severity="urgent")  # type: ignore[arg-type]