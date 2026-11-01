import asyncio

import pytest

from code_review_assistant.application.services.handle_github_installation_event import (
    HandleGitHubInstallationEvent,
)


class FakeInstallationWriter:
    def __init__(self) -> None:
        self.registered: list[tuple[str, int]] = []
        self.removed: list[int] = []

    async def register(self, organization_id: str, installation_id: int) -> None:
        self.registered.append((organization_id, installation_id))

    async def remove(self, installation_id: int) -> None:
        self.removed.append(installation_id)


def test_created_event_registers_lowercase_organization_login() -> None:
    writer = FakeInstallationWriter()
    handler = HandleGitHubInstallationEvent(writer)

    asyncio.run(
        handler.execute(
            "installation",
            {
                "action": "created",
                "installation": {
                    "id": 12345,
                    "account": {"type": "Organization", "login": "Acme-Engineering"},
                },
            },
        )
    )

    assert writer.registered == [("acme-engineering", 12345)]
    assert writer.removed == []


def test_deleted_event_removes_installation_mapping() -> None:
    writer = FakeInstallationWriter()
    handler = HandleGitHubInstallationEvent(writer)

    asyncio.run(
        handler.execute(
            "installation",
            {"action": "deleted", "installation": {"id": 12345}},
        )
    )

    assert writer.removed == [12345]
    assert writer.registered == []


def test_unrelated_event_is_ignored() -> None:
    writer = FakeInstallationWriter()
    handler = HandleGitHubInstallationEvent(writer)

    asyncio.run(handler.execute("push", {}))

    assert writer.registered == []
    assert writer.removed == []


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"action": "created"},
        {"action": "created", "installation": {"id": True}},
        {
            "action": "created",
            "installation": {
                "id": 1,
                "account": {"type": "User", "login": "someone"},
            },
        },
        {
            "action": "created",
            "installation": {
                "id": 1,
                "account": {"type": "Organization", "login": "  "},
            },
        },
    ],
)
def test_invalid_installation_event_fails_explicitly(payload: object) -> None:
    handler = HandleGitHubInstallationEvent(FakeInstallationWriter())

    with pytest.raises(ValueError):
        asyncio.run(handler.execute("installation", payload))