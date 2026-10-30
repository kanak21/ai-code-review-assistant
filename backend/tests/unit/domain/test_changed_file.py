import pytest

from code_review_assistant.domain.models.changed_file import (
    ChangeKind,
    ChangedFile,
)


def test_changed_file_keeps_patch_and_change_counts() -> None:
    file = ChangedFile(
        path="src/example.cs",
        kind=ChangeKind.MODIFIED,
        additions=2,
        deletions=1,
        patch="@@ -1 +1,2 @@",
    )

    assert file.path == "src/example.cs"
    assert file.patch == "@@ -1 +1,2 @@"


def test_renamed_file_requires_previous_path() -> None:
    with pytest.raises(ValueError, match="previous_path"):
        ChangedFile(
            path="src/new.cs",
            kind=ChangeKind.RENAMED,
            additions=0,
            deletions=0,
        )


@pytest.mark.parametrize("path", ["../outside.cs", "/absolute.cs", r"src\file.cs"])
def test_changed_file_rejects_unsafe_path(path: str) -> None:
    with pytest.raises(ValueError, match="relative POSIX path"):
        ChangedFile(
            path=path,
            kind=ChangeKind.MODIFIED,
            additions=0,
            deletions=0,
        )


def test_changed_file_rejects_negative_counts() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        ChangedFile(
            path="src/example.cs",
            kind=ChangeKind.MODIFIED,
            additions=-1,
            deletions=0,
        )