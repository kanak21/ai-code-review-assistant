import asyncio
from collections.abc import Callable

import httpx
import pytest

from code_review_assistant.domain.models.changed_file import ChangeKind
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.infrastructure.github_pull_request_reader import (
    GitHubPullRequestReader,
)


class FakeInstallationReader:
    def __init__(self) -> None:
        self.organization_ids: list[str] = []

    async def get_installation_id(self, organization_id: str) -> int:
        self.organization_ids.append(organization_id)
        return 67890


class FakeTokenProvider:
    def __init__(self) -> None:
        self.installation_ids: list[int] = []

    async def get_installation_token(self, installation_id: int) -> str:
        self.installation_ids.append(installation_id)
        return "test-installation-token"


def make_reader(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[GitHubPullRequestReader, FakeInstallationReader, FakeTokenProvider]:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.github.com",
    )
    installations = FakeInstallationReader()
    tokens = FakeTokenProvider()
    reader = GitHubPullRequestReader(client, installations, tokens)
    return reader, installations, tokens


def make_run(revision: str = "abc123") -> ReviewRun:
    return ReviewRun(
        organization_id="org-1",
        repository_id="acme/service",
        pull_request_number=42,
        revision=revision,
    )


def test_reader_fetches_and_maps_paginated_pull_request_files() -> None:
    filler_files = [
        {
            "filename": f"docs/file-{index}.md",
            "status": "modified",
            "additions": 1,
            "deletions": 0,
            "patch": "@@ -1 +1 @@\n+text",
        }
        for index in range(96)
    ]
    first_page = filler_files + [
        {
            "filename": "src/added.cs",
            "status": "added",
            "additions": 1,
            "deletions": 0,
            "patch": "@@ -0,0 +1 @@\n+new",
        },
        {
            "filename": "src/modified.cs",
            "status": "modified",
            "additions": 1,
            "deletions": 1,
            "patch": "@@ -1 +1 @@\n-old\n+new",
        },
        {
            "filename": "src/deleted.cs",
            "status": "removed",
            "additions": 0,
            "deletions": 1,
        },
        {
            "filename": "src/renamed.cs",
            "previous_filename": "src/old-name.cs",
            "status": "renamed",
            "additions": 1,
            "deletions": 0,
            "patch": "@@ -0,0 +1 @@\n+new",
        },
    ]
    second_page = [
        {
            "filename": "assets/image.png",
            "status": "modified",
            "additions": 0,
            "deletions": 0,
        }
    ]
    requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        if request.url.path == "/repos/acme/service/pulls/42":
            return httpx.Response(200, json={"head": {"sha": "abc123"}})

        if request.url.path == "/repos/acme/service/pulls/42/files":
            page = request.url.params.get("page")
            assert request.url.params.get("per_page") == "100"
            if page == "1":
                return httpx.Response(200, json=first_page)
            if page == "2":
                return httpx.Response(200, json=second_page)

        return httpx.Response(404, json={"message": "Unexpected request"})

    async def run():
        reader, installations, tokens = make_reader(handle_request)
        try:
            files = await reader.fetch_changed_files(make_run())
            return files, installations, tokens
        finally:
            await reader._http_client.aclose()

    files, installations, tokens = asyncio.run(run())

    assert len(files) == 101
    assert installations.organization_ids == ["org-1"]
    assert tokens.installation_ids == [67890]
    assert all(
        request.headers["Authorization"] == "Bearer test-installation-token"
        for request in requests
    )

    by_path = {file.path: file for file in files}
    assert by_path["src/added.cs"].kind is ChangeKind.ADDED
    assert by_path["src/modified.cs"].kind is ChangeKind.MODIFIED
    assert by_path["src/deleted.cs"].kind is ChangeKind.DELETED
    assert by_path["src/renamed.cs"].kind is ChangeKind.RENAMED
    assert by_path["src/renamed.cs"].previous_path == "src/old-name.cs"
    assert by_path["assets/image.png"].patch is None


def test_reader_rejects_pull_request_revision_mismatch() -> None:
    requested_paths: list[str] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/repos/acme/service/pulls/42":
            return httpx.Response(200, json={"head": {"sha": "newer-revision"}})
        return httpx.Response(200, json=[])

    async def run() -> None:
        reader, _, _ = make_reader(handle_request)
        try:
            await reader.fetch_changed_files(make_run("abc123"))
        finally:
            await reader._http_client.aclose()

    with pytest.raises(ValueError, match="revision"):
        asyncio.run(run())

    assert requested_paths == ["/repos/acme/service/pulls/42"]


def test_reader_surfaces_github_http_errors() -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Forbidden"})

    async def run() -> None:
        reader, _, _ = make_reader(handle_request)
        try:
            await reader.fetch_changed_files(make_run())
        finally:
            await reader._http_client.aclose()

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(run())