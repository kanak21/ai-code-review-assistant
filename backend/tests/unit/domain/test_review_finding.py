import pytest

from code_review_assistant.domain.models.review_finding import (
    ReviewFinding,
    Severity,
)


def test_review_finding_accepts_valid_evidence_and_location() -> None:
    finding = ReviewFinding(
        rule_id="CS001",
        severity=Severity.HIGH,
        title="Avoid this pattern",
        rationale="It can cause incorrect behavior.",
        file_path="src/example.cs",
        start_line=10,
        end_line=12,
        evidence="problematic code",
        standard_id="ORG-CSharp-01",
    )

    assert finding.start_line == 10
    assert finding.standard_id == "ORG-CSharp-01"


@pytest.mark.parametrize(
    ("start_line", "end_line"),
    [(0, 1), (3, 2)],
)
def test_review_finding_rejects_invalid_line_range(
    start_line: int,
    end_line: int,
) -> None:
    with pytest.raises(ValueError, match="line range"):
        ReviewFinding(
            rule_id="CS001",
            severity=Severity.HIGH,
            title="Avoid this pattern",
            rationale="It can cause incorrect behavior.",
            file_path="src/example.cs",
            start_line=start_line,
            end_line=end_line,
            evidence="problematic code",
        )