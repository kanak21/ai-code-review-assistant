from dataclasses import dataclass
from enum import Enum


class CheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    NOT_RUN = "not_run"


@dataclass(frozen=True, slots=True)
class CheckResult:
    check_id: str
    status: CheckStatus
    summary: str

    def __post_init__(self) -> None:
        if not isinstance(self.check_id, str) or not self.check_id.strip():
            raise ValueError("check_id must not be empty")

        if not isinstance(self.status, CheckStatus):
            raise ValueError("status must be a CheckStatus value")

        if not isinstance(self.summary, str) or not self.summary.strip():
            raise ValueError("summary must not be empty")