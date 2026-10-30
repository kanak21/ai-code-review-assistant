import asyncio

from code_review_assistant.application.ports.pull_request_reader import (
    PullRequestReader,
)
from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.review_run import ReviewRun


class FakePullRequestReader:
    def __init__(self, files: tuple[ChangedFile, ...]) -> None:
        self.files = files
        self.received_run: ReviewRun | None = None

    async def fetch_changed_files(
        self,
        run: ReviewRun,
    ) -> tuple[ChangedFile, ...]:
        self.received_run = run
        return self.files


def test_reader_port_accepts_provider_independent_implementation() -> None:
    run = ReviewRun("org-1", "repo-1", 42, "abc123")
    files = (ChangedFile("src/example.cs", ChangeKind.MODIFIED, 1, 0),)
    reader: PullRequestReader = FakePullRequestReader(files)

    result = asyncio.run(reader.fetch_changed_files(run))

    assert result == files
    assert isinstance(reader, FakePullRequestReader)
    assert reader.received_run == run