from dataclasses import dataclass

from code_review_assistant.domain.models.check_result import CheckResult
from code_review_assistant.domain.models.review_finding import ReviewFinding


@dataclass(frozen=True, slots=True)
class ReviewAnalysis:
    analyzed_paths: tuple[str, ...]
    findings: tuple[ReviewFinding, ...]
    checks: tuple[CheckResult, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.analyzed_paths, tuple) or not all(
            isinstance(path, str) and path.strip()
            for path in self.analyzed_paths
        ):
            raise ValueError("analyzed_paths must be a tuple of non-empty paths")

        if len(set(self.analyzed_paths)) != len(self.analyzed_paths):
            raise ValueError("analyzed_paths must not contain duplicates")

        if not isinstance(self.findings, tuple) or not all(
            isinstance(finding, ReviewFinding) for finding in self.findings
        ):
            raise ValueError("findings must be a tuple of ReviewFinding objects")

        if not isinstance(self.checks, tuple) or not all(
            isinstance(check, CheckResult) for check in self.checks
        ):
            raise ValueError("checks must be a tuple of CheckResult objects")