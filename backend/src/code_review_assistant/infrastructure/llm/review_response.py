from code_review_assistant.application.models.review_analysis import ReviewAnalysis
from code_review_assistant.domain.models.changed_file import ChangedFile
from code_review_assistant.domain.models.review_finding import ReviewFinding, Severity
from code_review_assistant.domain.models.standard import Standard
from code_review_assistant.domain.policies.diff_lines import added_line_numbers


def added_lines_by_file(
    files: tuple[ChangedFile, ...],
) -> dict[str, dict[int, str]]:
    result: dict[str, dict[int, str]] = {}

    for file in files:
        if file.patch is None:
            continue

        added_line_numbers(file.patch)
        lines: dict[int, str] = {}
        line_number = 0

        for line in file.patch.splitlines():
            if line.startswith("@@"):
                try:
                    new_range = line.split("+", 1)[1].split(" ", 1)[0]
                    line_number = int(new_range.split(",", 1)[0])
                except (IndexError, ValueError) as exc:
                    raise ValueError("malformed diff hunk header") from exc
            elif line.startswith("+"):
                lines[line_number] = line[1:]
                line_number += 1
            elif line.startswith(" "):
                line_number += 1

        result[file.path] = lines

    return result


def parse_review_payload(
    payload: object,
    analyzed_paths: tuple[str, ...],
    added_by_path: dict[str, dict[int, str]],
    standards: tuple[Standard, ...],
) -> ReviewAnalysis:
    if (
        not isinstance(payload, dict)
        or set(payload) != {"findings"}
        or not isinstance(payload["findings"], list)
    ):
        raise ValueError("review response must contain only a findings list")

    standards_by_id = {
        standard.standard_id: standard
        for standard in standards
        if standard.language.casefold() == "csharp"
    }
    required_fields = {
        "rule_id",
        "standard_id",
        "severity",
        "title",
        "rationale",
        "file_path",
        "start_line",
        "end_line",
        "evidence",
    }
    findings: list[ReviewFinding] = []

    for item in payload["findings"]:
        if not isinstance(item, dict) or set(item) != required_fields:
            raise ValueError("finding has an invalid shape")

        standard_id = item["standard_id"]
        if not isinstance(standard_id, str) or standard_id not in standards_by_id:
            raise ValueError("finding cites a standard not supplied to the analyzer")

        file_path = item["file_path"]
        if not isinstance(file_path, str) or file_path not in added_by_path:
            raise ValueError("finding must refer to an analyzed C# file")

        start_line = item["start_line"]
        end_line = item["end_line"]
        if (
            isinstance(start_line, bool)
            or not isinstance(start_line, int)
            or isinstance(end_line, bool)
            or not isinstance(end_line, int)
            or start_line < 1
            or end_line < start_line
        ):
            raise ValueError("finding has an invalid line range")

        added = added_by_path[file_path]
        line_numbers = range(start_line, end_line + 1)
        if any(line not in added for line in line_numbers):
            raise ValueError("finding lines must all be added lines")

        expected_evidence = "\n".join(added[line] for line in line_numbers)
        if item["evidence"] != expected_evidence:
            raise ValueError("finding evidence must exactly match added lines")

        findings.append(
            ReviewFinding(
                rule_id=item["rule_id"],
                severity=Severity(item["severity"]),
                title=item["title"],
                rationale=item["rationale"],
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                evidence=expected_evidence,
                standard_id=standards_by_id[standard_id].standard_id,
            )
        )

    return ReviewAnalysis(
        analyzed_paths=analyzed_paths,
        findings=tuple(findings),
        checks=(),
    )