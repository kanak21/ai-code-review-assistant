from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    rule_id: str
    severity: Severity
    title: str
    rationale: str
    file_path: str
    start_line: int
    end_line: int
    evidence: str
    standard_id: str | None = None

    def __post_init__(self) -> None:
        required_text = {
            "rule_id": self.rule_id,
            "title": self.title,
            "rationale": self.rationale,
            "file_path": self.file_path,
            "evidence": self.evidence,
        }
        for field_name, value in required_text.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")

        if not isinstance(self.severity, Severity):
            raise ValueError("severity must be a Severity value")

        for field_name, value in (
            ("start_line", self.start_line),
            ("end_line", self.end_line),
        ):
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{field_name} must be an integer")

        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError("line range must start at 1 or later and be ordered")

        if self.standard_id is not None and not self.standard_id.strip():
            raise ValueError("standard_id must not be empty when provided")