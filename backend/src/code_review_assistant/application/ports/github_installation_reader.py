from typing import Protocol


class GitHubInstallationReader(Protocol):
    async def get_installation_id(self, organization_id: str) -> int:
        """Return the trusted GitHub App installation ID for an organization."""
        ...