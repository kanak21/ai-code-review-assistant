import time

import httpx
import jwt

from code_review_assistant.settings import Settings


class GitHubAppTokenProvider:
    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient,
    ) -> None:
        if settings.github_app_id is None:
            raise RuntimeError("GITHUB_APP_ID must be configured")
        if settings.github_private_key_path is None:
            raise RuntimeError("GITHUB_PRIVATE_KEY_PATH must be configured")

        self._app_id = settings.github_app_id
        self._private_key_path = settings.github_private_key_path
        self._http_client = http_client

    async def get_installation_token(self, installation_id: int) -> str:
        if (
            not isinstance(installation_id, int)
            or isinstance(installation_id, bool)
            or installation_id < 1
        ):
            raise ValueError("installation_id must be a positive integer")

        try:
            private_key = self._private_key_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError("Could not read the GitHub App private key file") from exc

        now = int(time.time())
        app_jwt = jwt.encode(
            {
                "iat": now - 60,
                "exp": now + 540,
                "iss": str(self._app_id),
            },
            private_key,
            algorithm="RS256",
        )

        response = await self._http_client.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {app_jwt}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={},
        )
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("GitHub returned an invalid installation-token response")

        token = payload.get("token")
        if not isinstance(token, str) or not token.strip():
            raise RuntimeError("GitHub response did not contain an installation token")

        return token