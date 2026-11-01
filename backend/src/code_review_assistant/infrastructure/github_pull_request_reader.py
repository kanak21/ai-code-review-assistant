from typing import Protocol

import httpx

from code_review_assistant.application.ports.github_installation_reader import (
    GitHubInstallationReader,
)
from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.review_run import ReviewRun


class _InstallationTokenProvider(Protocol):
    async def get_installation_token(self, installation_id: int) -> str: ...


class GitHubPullRequestReader:
    _API_URL = "https://api.github.com"
    _PER_PAGE = 100
    _MAX_PAGES = 30

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        installation_reader: GitHubInstallationReader,
        token_provider: _InstallationTokenProvider,
    ) -> None:
        self._http_client = http_client
        self._installation_reader = installation_reader
        self._token_provider = token_provider

    async def fetch_changed_files(
        self,
        run: ReviewRun,
    ) -> tuple[ChangedFile, ...]:
        if not isinstance(run, ReviewRun):
            raise ValueError("run must be a ReviewRun")

        repository_parts = run.repository_id.split("/")
        if len(repository_parts) != 2 or any(
            not part or part in {".", ".."} for part in repository_parts
        ):
            raise ValueError("repository_id must be a GitHub owner/repo slug")

        installation_id = await self._installation_reader.get_installation_id(
            run.organization_id
        )
        token = await self._token_provider.get_installation_token(installation_id)
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        repository_url = (
            f"{self._API_URL}/repos/{run.repository_id}/pulls/"
            f"{run.pull_request_number}"
        )
        pull_request_response = await self._http_client.get(
            repository_url,
            headers=headers,
        )
        pull_request_response.raise_for_status()

        pull_request = pull_request_response.json()
        if not isinstance(pull_request, dict):
            raise RuntimeError("GitHub returned an invalid pull-request response")

        head = pull_request.get("head")
        if not isinstance(head, dict):
            raise RuntimeError("GitHub pull-request response has no head")

        current_revision = head.get("sha")
        if not isinstance(current_revision, str) or not current_revision:
            raise RuntimeError("GitHub pull-request response has no head revision")
        if current_revision != run.revision:
            raise ValueError("pull-request revision does not match the requested review")

        files_url = f"{repository_url}/files"
        files: list[ChangedFile] = []

        for page in range(1, self._MAX_PAGES + 1):
            response = await self._http_client.get(
                files_url,
                headers=headers,
                params={"per_page": self._PER_PAGE, "page": page},
            )
            response.raise_for_status()

            payload = response.json()
            if not isinstance(payload, list):
                raise RuntimeError("GitHub returned an invalid pull-request files response")

            files.extend(self._parse_file(item) for item in payload)

            if len(payload) < self._PER_PAGE:
                return tuple(files)

        raise RuntimeError(
            f"Pull request file list exceeded the supported limit of "
            f"{self._PER_PAGE * self._MAX_PAGES} files"
        )

    @staticmethod
    def _parse_file(item: object) -> ChangedFile:
        if not isinstance(item, dict):
            raise RuntimeError("GitHub returned an invalid changed-file entry")

        path = item.get("filename")
        status = item.get("status")
        additions = item.get("additions")
        deletions = item.get("deletions")
        patch = item.get("patch")

        if not isinstance(path, str):
            raise RuntimeError("GitHub changed-file entry has no valid filename")
        if (
            not isinstance(additions, int)
            or isinstance(additions, bool)
            or not isinstance(deletions, int)
            or isinstance(deletions, bool)
        ):
            raise RuntimeError("GitHub changed-file entry has invalid line counts")
        if patch is not None and not isinstance(patch, str):
            raise RuntimeError("GitHub changed-file entry has an invalid patch")

        kinds = {
            "added": ChangeKind.ADDED,
            "modified": ChangeKind.MODIFIED,
            "removed": ChangeKind.DELETED,
            "renamed": ChangeKind.RENAMED,
        }
        kind = kinds.get(status) if isinstance(status, str) else None
        if kind is None:
            raise RuntimeError(f"GitHub returned unsupported file status: {status!r}")

        if kind is ChangeKind.RENAMED:
            previous_path = item.get("previous_filename")
            if not isinstance(previous_path, str):
                raise RuntimeError("GitHub renamed-file entry has no previous filename")
            return ChangedFile(
                path=path,
                kind=kind,
                additions=additions,
                deletions=deletions,
                patch=patch,
                previous_path=previous_path,
            )

        return ChangedFile(
            path=path,
            kind=kind,
            additions=additions,
            deletions=deletions,
            patch=patch,
        )