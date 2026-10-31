from code_review_assistant.infrastructure.database.base import Base
from code_review_assistant.infrastructure.database.standard_record import StandardRecord


def test_standard_record_has_organization_version_key() -> None:
    table = Base.metadata.tables["standards"]

    assert table is StandardRecord.__table__
    assert {
        "organization_id",
        "standard_id",
        "version",
        "title",
        "guidance",
        "source",
        "enforcement",
        "language",
        "category",
        "severity",
    }.issubset(table.columns.keys())

    unique_constraints = [
        constraint
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    ]
    assert any(
        {column.name for column in constraint.columns}
        == {"organization_id", "standard_id", "version"}
        for constraint in unique_constraints
    )