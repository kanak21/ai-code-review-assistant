import pytest

from code_review_assistant.domain.models.standard import (
    Enforcement,
    Standard,
)


def test_standard_preserves_version_and_provenance() -> None:
    standard = Standard(
        standard_id="ORG-CSharp-01",
        version="2026-01",
        title="Use cancellation tokens",
        guidance="Pass cancellation tokens through asynchronous calls.",
        source="engineering/async-guidance.md",
        enforcement=Enforcement.MANDATORY,
        language="csharp",
    )

    assert standard.version == "2026-01"
    assert standard.source == "engineering/async-guidance.md"


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
        )