import asyncio

import pytest

from code_review_assistant.infrastructure.database.github_installation_writer import (
    SqlAlchemyGitHubInstallationWriter,
)


class UnexpectedSessionFactory:
    def begin(self) -> None:
        raise AssertionError("database should not be accessed for invalid input")


@pytest.mark.parametrize("organization_id", ["", "  ", None, 123])
def test_register_rejects_invalid_organization_id(organization_id: object) -> None:
    writer = SqlAlchemyGitHubInstallationWriter(UnexpectedSessionFactory())

    with pytest.raises(ValueError, match="organization_id"):
        asyncio.run(writer.register(organization_id, 123))  # type: ignore[arg-type]


@pytest.mark.parametrize("installation_id", [0, -1, True, 1.5])
def test_register_rejects_invalid_installation_id(installation_id: object) -> None:
    writer = SqlAlchemyGitHubInstallationWriter(UnexpectedSessionFactory())

    with pytest.raises(ValueError, match="installation_id"):
        asyncio.run(writer.register("org-1", installation_id))  # type: ignore[arg-type]


@pytest.mark.parametrize("installation_id", [0, -1, True, 1.5])
def test_remove_rejects_invalid_installation_id(installation_id: object) -> None:
    writer = SqlAlchemyGitHubInstallationWriter(UnexpectedSessionFactory())

    with pytest.raises(ValueError, match="installation_id"):
        asyncio.run(writer.remove(installation_id))  # type: ignore[arg-type]