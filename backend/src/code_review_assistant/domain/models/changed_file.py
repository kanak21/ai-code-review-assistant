from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath


class ChangeKind(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


@dataclass(frozen=True, slots=True)
class ChangedFile:
    path: str
    kind: ChangeKind
    additions: int
    deletions: int
    patch: str | None = None
    previous_path: str | None = None

    def __post_init__(self) -> None:
        self._validate_path("path", self.path)

        if not isinstance(self.kind, ChangeKind):
            raise ValueError("kind must be a ChangeKind value")

        for field_name, value in (
            ("additions", self.additions),
            ("deletions", self.deletions),
        ):
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{field_name} must be an integer")
            if value < 0:
                raise ValueError(f"{field_name} must not be negative")

        if self.patch is not None and not isinstance(self.patch, str):
            raise ValueError("patch must be text or None")

        if self.kind is ChangeKind.RENAMED:
            if self.previous_path is None:
                raise ValueError("renamed files require previous_path")
            self._validate_path("previous_path", self.previous_path)
        elif self.previous_path is not None:
            raise ValueError("previous_path is only valid for renamed files")

    @staticmethod
    def _validate_path(field_name: str, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must not be empty")
        if "\\" in value or "\x00" in value:
            raise ValueError(f"{field_name} must be a relative POSIX path")

        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"{field_name} must be a relative POSIX path")