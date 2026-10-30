from dataclasses import dataclass
from enum import Enum


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

    def __post_init__(self) -> None:
        for field_name, value in (
            ("standard_id", self.standard_id),
            ("version", self.version),
            ("title", self.title),
            ("guidance", self.guidance),
            ("source", self.source),
            ("language", self.language),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")

        if not isinstance(self.enforcement, Enforcement):
            raise ValueError("enforcement must be an Enforcement value")