from dataclasses import dataclass

from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.check_result import CheckResult
from code_review_assistant.domain.models.review_coverage import ReviewCoverage
from code_review_assistant.domain.models.review_finding import ReviewFinding
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.policies.diff_lines import added_line_numbers

@dataclass(frozen=True, slots=True)
class ReviewResult:
    run: ReviewRun
    changed_files: tuple[ChangedFile, ...]
    findings: tuple[ReviewFinding, ...]
    checks: tuple[CheckResult, ...]
    coverage: ReviewCoverage

    def __post_init__(self) -> None:
        if not isinstance(self.run, ReviewRun):
            raise ValueError("run must be a ReviewRun")

        if not isinstance(self.coverage, ReviewCoverage):
            raise ValueError("coverage must be a ReviewCoverage")

        for field_name, values, item_type in (
            ("changed_files", self.changed_files, ChangedFile),
            ("findings", self.findings, ReviewFinding),
            ("checks", self.checks, CheckResult),
        ):
            if not isinstance(values, tuple) or not all(
                isinstance(value, item_type) for value in values
            ):
                raise ValueError(f"{field_name} must be a tuple of {item_type.__name__}")

        paths = [changed_file.path for changed_file in self.changed_files]
        if len(paths) != len(set(paths)):
            raise ValueError("changed file paths must be unique")

        if self.coverage.changed_files != len(self.changed_files):
            raise ValueError("coverage changed_files must match changed files")

        files_by_path = {changed_file.path: changed_file for changed_file in self.changed_files}
        for finding in self.findings:
            changed_file = files_by_path.get(finding.file_path)
            if changed_file is None:
                raise ValueError("each finding must refer to a changed file")
            if changed_file.kind is ChangeKind.DELETED:
                raise ValueError("findings cannot refer to deleted files")

            if changed_file.patch is None:
                raise ValueError("cannot validate finding location without a patch")

            added_lines = added_line_numbers(changed_file.patch)
            if not all(
                line in added_lines
                for line in range(finding.start_line, finding.end_line + 1)
            ):
                raise ValueError("finding lines must all be added lines")
