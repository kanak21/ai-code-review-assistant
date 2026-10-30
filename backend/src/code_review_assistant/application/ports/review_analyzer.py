from typing import Protocol

from code_review_assistant.application.models.review_analysis import ReviewAnalysis
from code_review_assistant.domain.models.changed_file import ChangedFile
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.models.standard import Standard


class ReviewAnalyzer(Protocol):
    async def analyze(
        self,
        run: ReviewRun,
        changed_files: tuple[ChangedFile, ...],
        standards: tuple[Standard, ...],
    ) -> ReviewAnalysis:
        """Analyze bounded PR changes against the supplied standards."""
        ...