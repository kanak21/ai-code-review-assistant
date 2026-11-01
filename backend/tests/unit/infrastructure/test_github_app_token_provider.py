import asyncio
from datetime import datetime, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from code_review_assistant.infrastructure.github_app_token_provider import (
    GitHubAppTokenProvider,
)
from code_review_assistant.settings import Settings


def make_key_pair() -> tuple[str, object]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return private_pem, private_key.public_key()


def test_provider_exchanges_app_jwt_for_installation_token(tmp_path) -> None:
    private_pem, public_key = make_key_pair()
    key_path = tmp_path / "github-app.pem"
    key_path.write_text(private_pem, encoding="utf-8")
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        github_app_id=12345,
        github_private_key_path=key_path,
    )

    def handle_request(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/app/installations/67890/access_tokens"
        assert request.headers["Accept"] == "application/vnd.github+json"
        assert request.headers["X-GitHub-Api-Version"] == "2022-11-28"

        authorization = request.headers["Authorization"]
        assert authorization.startswith("Bearer ")
        app_jwt = authorization.removeprefix("Bearer ")
        claims = jwt.decode(
            app_jwt,
            public_key,
            algorithms=["RS256"],
            options={"verify_exp": False, "verify_iat": False},
        )
        assert claims["iss"] == str(settings.github_app_id)
        assert claims["exp"] - claims["iat"] == 600

        return httpx.Response(201, json={"token": "test-installation-token"})

    async def run() -> str:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle_request),
            base_url="https://api.github.com",
        ) as client:
            provider = GitHubAppTokenProvider(settings, client)
            return await provider.get_installation_token(67890)

    assert asyncio.run(run()) == "test-installation-token"


def test_provider_surfaces_github_http_errors(tmp_path) -> None:
    private_pem, _ = make_key_pair()
    key_path = tmp_path / "github-app.pem"
    key_path.write_text(private_pem, encoding="utf-8")
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        github_app_id=12345,
        github_private_key_path=key_path,
    )

    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Forbidden"})

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle_request),
            base_url="https://api.github.com",
        ) as client:
            provider = GitHubAppTokenProvider(settings, client)
            await provider.get_installation_token(67890)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(run())


@pytest.mark.parametrize("installation_id", [0, -1, True, 1.5])
def test_provider_rejects_invalid_installation_id(
    tmp_path,
    installation_id: object,
) -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        github_app_id=12345,
        github_private_key_path=tmp_path / "not-read.pem",
    )
    request_count = 0

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, json={"token": "unexpected"})

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle_request),
        ) as client:
            provider = GitHubAppTokenProvider(settings, client)
            await provider.get_installation_token(installation_id)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="installation_id"):
        asyncio.run(run())

    assert request_count == 0


def test_provider_rejects_missing_app_configuration() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        github_app_id=None,
        github_private_key_path=None,
    )

    with pytest.raises(RuntimeError, match="GITHUB_APP_ID"):
        GitHubAppTokenProvider(settings, httpx.AsyncClient())


@pytest.mark.parametrize(
    "payload",
    [[], {}, {"token": ""}, {"token": "   "}, {"token": 123}],
)
def test_provider_rejects_malformed_token_response(tmp_path, payload: object) -> None:
    private_pem, _ = make_key_pair()
    key_path = tmp_path / "github-app.pem"
    key_path.write_text(private_pem, encoding="utf-8")
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        github_app_id=12345,
        github_private_key_path=key_path,
    )

    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json=payload)

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle_request),
            base_url="https://api.github.com",
        ) as client:
            provider = GitHubAppTokenProvider(settings, client)
            await provider.get_installation_token(67890)

    with pytest.raises(
        RuntimeError,
        match="invalid installation-token response|did not contain an installation token",
    ):
        asyncio.run(run())