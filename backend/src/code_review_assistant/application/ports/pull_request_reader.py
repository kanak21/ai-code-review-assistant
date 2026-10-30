from typing import Protocol

from code_review_assistant.domain.models.changed_file import ChangedFile
from code_review_assistant.domain.models.review_run import ReviewRun


class PullRequestReader(Protocol):
    async def fetch_changed_files(
        self,
        run: ReviewRun,
    ) -> tuple[ChangedFile, ...]:
        """Fetch the changed files for this exact review run."""
        ...