from code_review_assistant.application.models.review_analysis import ReviewAnalysis
from code_review_assistant.application.ports.pull_request_reader import (
    PullRequestReader,
)
from code_review_assistant.application.ports.review_analyzer import ReviewAnalyzer
from code_review_assistant.application.ports.standards_reader import StandardsReader
from code_review_assistant.domain.models.changed_file import ChangedFile
from code_review_assistant.domain.models.review_coverage import ReviewCoverage
from code_review_assistant.domain.models.review_result import ReviewResult
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.models.standard import Standard


class ReviewPullRequest:
    def __init__(
        self,
        pull_request_reader: PullRequestReader,
        standards_reader: StandardsReader,
        analyzer: ReviewAnalyzer,
    ) -> None:
        self._pull_request_reader = pull_request_reader
        self._standards_reader = standards_reader
        self._analyzer = analyzer

    async def execute(self, run: ReviewRun) -> ReviewResult:
        changed_files = await self._pull_request_reader.fetch_changed_files(run)
        if not isinstance(changed_files, tuple) or not all(
            isinstance(file, ChangedFile) for file in changed_files
        ):
            raise ValueError("pull request reader must return ChangedFile objects")

        standards = await self._standards_reader.get_applicable_standards(
            run,
            changed_files,
        )
        if not isinstance(standards, tuple) or not all(
            isinstance(standard, Standard) for standard in standards
        ):
            raise ValueError("standards reader must return Standard objects")

        analysis = await self._analyzer.analyze(run, changed_files, standards)
        if not isinstance(analysis, ReviewAnalysis):
            raise ValueError("analyzer must return a ReviewAnalysis")

        changed_paths = {file.path for file in changed_files}
        analyzed_paths = set(analysis.analyzed_paths)
        if not analyzed_paths.issubset(changed_paths):
            raise ValueError("analyzer reported files outside the pull request")

        if any(finding.file_path not in analyzed_paths for finding in analysis.findings):
            raise ValueError("findings must refer to analyzed files")

        valid_standard_ids = {standard.standard_id for standard in standards}
        if any(
            finding.standard_id is not None
            and finding.standard_id not in valid_standard_ids
            for finding in analysis.findings
        ):
            raise ValueError("finding cites a standard not supplied to the analyzer")

        coverage = ReviewCoverage(
            changed_files=len(changed_files),
            analyzed_files=len(analyzed_paths),
        )

        return ReviewResult(
            run=run,
            changed_files=changed_files,
            findings=analysis.findings,
            checks=analysis.checks,
            coverage=coverage,
        )