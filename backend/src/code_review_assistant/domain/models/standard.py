from dataclasses import dataclass
from enum import Enum

from code_review_assistant.domain.models.review_finding import Severity


class Enforcement(str, Enum):
    MANDATORY = "mandatory"
    RECOMMENDED = "recommended"


@dataclass(frozen=True, slots=True)
class Standard:
    standard_id: str
    version: str
    title: str
    guidance: str
    source: str
    enforcement: Enforcement
    language: str
    category: str
    severity: Severity

    def __post_init__(self) -> None:
        for field_name, value in (
            ("standard_id", self.standard_id),
            ("version", self.version),
            ("title", self.title),
            ("guidance", self.guidance),
            ("source", self.source),
            ("language", self.language),
            ("category", self.category),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")

        if not isinstance(self.enforcement, Enforcement):
            raise ValueError("enforcement must be an Enforcement value")
        if not isinstance(self.severity, Severity):
            raise ValueError("severity must be a Severity value")