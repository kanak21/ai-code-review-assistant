from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReviewRun:
    organization_id: str
    repository_id: str
    pull_request_number: int
    revision: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("organization_id", self.organization_id),
            ("repository_id", self.repository_id),
            ("revision", self.revision),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")

        if (
            not isinstance(self.pull_request_number, int)
            or isinstance(self.pull_request_number, bool)
            or self.pull_request_number < 1
        ):
            raise ValueError("pull_request_number must be a positive integer")

    def is_stale_for(self, current_revision: str) -> bool:
        if not isinstance(current_revision, str) or not current_revision.strip():
            raise ValueError("current_revision must not be empty")

        return self.revision != current_revision