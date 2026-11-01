from code_review_assistant.application.ports.github_installation_writer import (
    GitHubInstallationWriter,
)


class HandleGitHubInstallationEvent:
    def __init__(self, writer: GitHubInstallationWriter) -> None:
        self._writer = writer

    async def execute(self, event_name: str, payload: object) -> None:
        if event_name != "installation":
            return
        if not isinstance(payload, dict):
            raise ValueError("GitHub installation event payload must be an object")

        action = payload.get("action")
        if action not in {"created", "deleted"}:
            return

        installation = payload.get("installation")
        if not isinstance(installation, dict):
            raise ValueError("GitHub installation event has no installation object")

        installation_id = installation.get("id")
        if (
            not isinstance(installation_id, int)
            or isinstance(installation_id, bool)
            or installation_id < 1
        ):
            raise ValueError("GitHub installation event has an invalid installation ID")

        if action == "deleted":
            await self._writer.remove(installation_id)
            return

        account = installation.get("account")
        if not isinstance(account, dict) or account.get("type") != "Organization":
            raise ValueError("GitHub installation must belong to an organization")

        login = account.get("login")
        if not isinstance(login, str) or not login.strip():
            raise ValueError("GitHub organization account has no valid login")

        await self._writer.register(login.strip().casefold(), installation_id)