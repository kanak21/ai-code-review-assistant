import asyncio
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR / "src"))

from sqlalchemy import select

from code_review_assistant.domain.models.review_finding import Severity
from code_review_assistant.domain.models.standard import Enforcement, Standard
from code_review_assistant.infrastructure.database.engine import (
    create_database_engine,
    create_session_factory,
)
from code_review_assistant.infrastructure.database.standard_record import (
    StandardRecord,
)
from code_review_assistant.infrastructure.database.standards_writer import (
    SqlAlchemyStandardsWriter,
)
from code_review_assistant.settings import Settings


EXPECTED_ORGANIZATION_ID = "demo-org"
TEST_DATABASE = "review_assistant_test"
JSON_PATH = BACKEND_DIR / "demo_standards.json"


def load_standards() -> tuple[Standard, ...]:
    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        raise ValueError("The JSON root must be an object")

    organization_id = payload.get("organization_id")
    if organization_id != EXPECTED_ORGANIZATION_ID:
        raise ValueError(
            f"Expected organization_id {EXPECTED_ORGANIZATION_ID!r}, "
            f"got {organization_id!r}"
        )

    entries = payload.get("standards")
    if not isinstance(entries, list) or len(entries) != 20:
        raise ValueError("Expected exactly 20 standards in the JSON file")

    standards = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each standard must be a JSON object")

        standards.append(
            Standard(
                standard_id=entry["standard_id"],
                version=entry["version"],
                title=entry["title"],
                guidance=entry["guidance"],
                source=entry["source"],
                enforcement=Enforcement(entry["enforcement"]),
                language=entry["language"],
                category=entry["category"],
                severity=Severity(entry["severity"]),
            )
        )

    identities = [(standard.standard_id, standard.version) for standard in standards]
    if len(set(identities)) != len(identities):
        raise ValueError("The JSON contains duplicate standard IDs and versions")

    return tuple(standards)


async def import_standards(standards: tuple[Standard, ...]) -> None:
    settings = Settings().model_copy(update={"postgres_db": TEST_DATABASE})
    engine = create_database_engine(settings)

    try:
        session_factory = create_session_factory(engine)

        async with session_factory() as session:
            existing_id = await session.scalar(
                select(StandardRecord.id)
                .where(
                    StandardRecord.organization_id == EXPECTED_ORGANIZATION_ID
                )
                .limit(1)
            )

        if existing_id is not None:
            raise RuntimeError(
                f"{EXPECTED_ORGANIZATION_ID!r} already has standards in "
                f"{TEST_DATABASE!r}; refusing to insert duplicates."
            )

        writer = SqlAlchemyStandardsWriter(session_factory)
        await writer.add_many(EXPECTED_ORGANIZATION_ID, standards)
    finally:
        await engine.dispose()


def main() -> None:
    standards = load_standards()
    print(f"Target database: {TEST_DATABASE}")
    print(f"Organization: {EXPECTED_ORGANIZATION_ID}")
    print(f"Standards to import: {len(standards)}")

    asyncio.run(
        import_standards(standards),
        loop_factory=asyncio.SelectorEventLoop,
    )
    print("Import completed successfully.")


if __name__ == "__main__":
    main()