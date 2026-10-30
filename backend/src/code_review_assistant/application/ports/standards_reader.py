from typing import Protocol

from code_review_assistant.domain.models.changed_file import ChangedFile
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.models.standard import Standard


class StandardsReader(Protocol):
    async def get_applicable_standards(
        self,
        run: ReviewRun,
        changed_files: tuple[ChangedFile, ...],
    ) -> tuple[Standard, ...]:
        """Return standards applicable to this review and its changed files."""
        ...