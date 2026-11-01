import re

from code_review_assistant.application.models.review_analysis import ReviewAnalysis
from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.review_finding import ReviewFinding
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.models.standard import Standard
from code_review_assistant.domain.policies.diff_lines import added_line_numbers


_STANDARD_ID = "DEMO-CS-02"
_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_BLOCKING_ASYNC = re.compile(r"\.Result\b|\.Wait\s*\(")


def _added_lines(patch: str) -> tuple[tuple[int, str], ...]:
    added_line_numbers(patch)  # Validate the unified diff before reading it.

    results: list[tuple[int, str]] = []
    new_line_number = 0

    for line in patch.splitlines():
        if line.startswith("@@"):
            match = _HUNK_HEADER.match(line)
            if match is None:
                raise ValueError("malformed diff hunk header")
            new_line_number = int(match.group(1))
        elif line.startswith("+"):
            results.append((new_line_number, line[1:]))
            new_line_number += 1
        elif line.startswith(" "):
            new_line_number += 1

    return tuple(results)


class CSharpStandardsAnalyzer:
    async def analyze(
        self,
        run: ReviewRun,
        changed_files: tuple[ChangedFile, ...],
        standards: tuple[Standard, ...],
    ) -> ReviewAnalysis:
        del run

        blocking_standards = tuple(
            standard
            for standard in standards
            if standard.standard_id == _STANDARD_ID
            and standard.language.casefold() == "csharp"
        )

        analyzed_paths: list[str] = []
        findings: list[ReviewFinding] = []

        for changed_file in changed_files:
            if (
                not changed_file.path.casefold().endswith(".cs")
                or changed_file.kind is ChangeKind.DELETED
                or changed_file.patch is None
            ):
                continue

            analyzed_paths.append(changed_file.path)

            for line_number, added_line in _added_lines(changed_file.patch):
                if not _BLOCKING_ASYNC.search(added_line):
                    continue

                for standard in blocking_standards:
                    findings.append(
                        ReviewFinding(
                            rule_id=standard.standard_id,
                            severity=standard.severity,
                            title=standard.title,
                            rationale=standard.guidance,
                            file_path=changed_file.path,
                            start_line=line_number,
                            end_line=line_number,
                            evidence=added_line,
                            standard_id=standard.standard_id,
                        )
                    )

        return ReviewAnalysis(
            analyzed_paths=tuple(analyzed_paths),
            findings=tuple(findings),
            checks=(),
        )