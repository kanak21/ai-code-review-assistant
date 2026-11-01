from typing import Protocol


class GitHubInstallationWriter(Protocol):
    async def register(
        self,
        organization_id: str,
        installation_id: int,
    ) -> None:
        """Create or update an organization's GitHub App installation mapping."""
        ...

    async def remove(self, installation_id: int) -> None:
        """Remove a mapping when the GitHub App is uninstalled."""
        ...