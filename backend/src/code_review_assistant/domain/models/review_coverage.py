from dataclasses import dataclass
from enum import Enum


class CoverageStatus(str, Enum):
    NO_CHANGES = "no_changes"
    NOT_STARTED = "not_started"
    PARTIAL = "partial"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class ReviewCoverage:
    changed_files: int
    analyzed_files: int

    def __post_init__(self) -> None:
        for field_name, value in (
            ("changed_files", self.changed_files),
            ("analyzed_files", self.analyzed_files),
        ):
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{field_name} must be an integer")
            if value < 0:
                raise ValueError(f"{field_name} must not be negative")

        if self.analyzed_files > self.changed_files:
            raise ValueError("analyzed_files cannot exceed changed_files")

    @property
    def status(self) -> CoverageStatus:
        if self.changed_files == 0:
            return CoverageStatus.NO_CHANGES
        if self.analyzed_files == 0:
            return CoverageStatus.NOT_STARTED
        if self.analyzed_files == self.changed_files:
            return CoverageStatus.COMPLETE
        return CoverageStatus.PARTIAL

    @property
    def percentage(self) -> float | None:
        if self.changed_files == 0:
            return None
        return self.analyzed_files / self.changed_files * 100