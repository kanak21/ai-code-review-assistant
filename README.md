# AI Code Review Assistant

A Python backend that receives GitHub pull-request webhooks, queues review jobs,
retrieves relevant organization standards, and analyzes changed C# code using
Anthropic or a local Ollama model. Review jobs and findings are stored in
PostgreSQL with pgvector.

> **Project status:** Development prototype. The backend stores review findings
> but does not yet publish review comments to GitHub. It currently accepts
> organization-owned repositories and analyzes changed `.cs` files.

## What it does

1. Receives GitHub App installation and pull-request webhooks.
2. Records organization installations and queues supported PR events.
3. A background worker claims queued jobs and reads the pull-request diff.
4. Relevant engineering standards are retrieved using text embeddings.
5. The configured review model checks changed C# lines against those standards.
6. Job status, review metadata, and findings are saved in PostgreSQL.

Supported PR actions: `opened`, `reopened`, `synchronize`, and
`ready_for_review`.

## Architecture

```text
GitHub
  │ HTTPS webhook
  ▼
FastAPI backend ── validates signature
  │
  ├── installation event ── saves installation ID
  └── pull_request event ── enqueues review job
                                  │
                                  ▼
                         PostgreSQL + pgvector
                                  │
                                  ▼
                         Review worker
                          ├── GitHub App token
                          ├── PR diff reader
                          ├── standards retrieval
                          ├── Ollama or Anthropic review
                          └── persists findings
```

The code is organized into:

- `backend/src/code_review_assistant/domain/` — core review and standard models.
- `backend/src/code_review_assistant/application/` — review workflow, job processing,
  and service ports.
- `backend/src/code_review_assistant/infrastructure/` — FastAPI webhook, GitHub,
  database, and model adapters.
- `backend/tests/unit/` and `backend/tests/integration/` — automated tests.
- `backend/migrations/versions/` — Alembic database migrations.

## Requirements

- Git and Windows PowerShell (commands below use PowerShell syntax).
- Python 3.12 or later recommended.
- Docker Desktop with Docker Compose.
- Ollama and the models below for local-model review and embedding integration tests.
- A GitHub App, organization, and public HTTPS webhook URL (for live GitHub testing).

The package metadata currently declares Python `>=3.10`; Windows users should use a
recent Python version because async Psycopg requires a Selector event loop.

## Configure environment

Create or update the repository-root `.env` file. Do not commit it or share its
contents.

```dotenv
POSTGRES_DB=review_assistant
POSTGRES_USER=review_assistant
POSTGRES_PASSWORD=replace-with-a-local-password
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432

REVIEW_PROVIDER=ollama
REVIEW_MODEL=llama3.2:latest
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text:latest
EMBEDDING_DIMENSIONS=768
OLLAMA_BASE_URL=http://127.0.0.1:11434

GITHUB_APP_ID=your-app-id
GITHUB_PRIVATE_KEY_PATH="C:\path\to\your-app-private-key.pem"
GITHUB_WEBHOOK_ENABLED=true
GITHUB_WEBHOOK_SECRET=the-same-secret-configured-in-github
```

For Anthropic reviews or OpenAI embeddings, select the corresponding provider and
configure its API key. Never put a private key, API token, or real webhook secret in
source control.

## Set up the backend

From the repository root:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Start PostgreSQL from the repository root in another terminal:

```powershell
cd C:\path\to\ai-code-review-assistant
docker compose up -d db
```

Apply migrations from the `backend` directory:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

For local Ollama use:

```powershell
ollama pull llama3.2:latest
ollama pull nomic-embed-text:latest
```

## Run locally

Keep PostgreSQL and Ollama running.

Start the API in a terminal from `backend`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn code_review_assistant.main:app --reload --host 127.0.0.1 --port 8000
```

Verify the API:

```text
http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

Start the worker in a second terminal from `backend`:

```powershell
.\.venv\Scripts\python.exe -c "import asyncio; from code_review_assistant.worker import run_worker; asyncio.run(run_worker(), loop_factory=asyncio.SelectorEventLoop)"
```

The worker polls the queue and can appear idle when there are no jobs. Keep both
the API and worker running.

## Configure a GitHub App

1. Create a GitHub App owned by the organization that owns the test repository.
2. Configure a webhook URL that GitHub can reach. For local development, expose
   port `8000` through an HTTPS tunnel, then use:
   `https://YOUR-TUNNEL-HOST/webhooks/github`.
3. Configure the same webhook secret in GitHub and the local `.env`.
4. Subscribe to **Installation** and **Pull request** events.
5. Grant the repository permissions needed to read pull requests. Add write
   permission only when review publishing is implemented and required.
6. Generate a private key and set `GITHUB_PRIVATE_KEY_PATH` to the downloaded
   `.pem` file.
7. Install the app on the organization and select the test repository.
8. Restart the API and worker after changing `.env`.

The current webhook handler requires the repository owner type to be
`Organization`. Installing the app on an organization does not transfer a
personal repository into that organization.

## Load organization standards

`backend/demo_standards.json` is sample data and includes a C# rule for avoiding
blocking asynchronous code. The current repository does not yet provide a
standalone command or HTTP endpoint for importing this JSON into PostgreSQL and
indexing it. Standards must be present in the database and embedded before they
can be retrieved during reviews.

## Test

Run the normal test suite from `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

PostgreSQL integration tests use the separate `review_assistant_test` database.
Create it if needed:

```powershell
docker compose exec db psql -U review_assistant -d postgres -c "CREATE DATABASE review_assistant_test OWNER review_assistant;"
```

Set `POSTGRES_DB=review_assistant_test` temporarily in the shell and apply
migrations to that database before running database integration tests:

```powershell
$env:POSTGRES_DB = "review_assistant_test"
.\.venv\Scripts\python.exe -m alembic upgrade head
Remove-Item Env:POSTGRES_DB
```

Enable PostgreSQL tests:

```powershell
$env:RUN_DB_INTEGRATION_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest tests\integration -q
```

Enable live Ollama integration tests too. These call the local Ollama server and
may take longer:

```powershell
$env:RUN_OLLAMA_INTEGRATION_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest tests\integration -q
```

The end-to-end Ollama/PostgreSQL pipeline test requires both flags. Remove the
flags when finished if you want subsequent runs to skip those tests:

```powershell
Remove-Item Env:RUN_DB_INTEGRATION_TESTS -ErrorAction SilentlyContinue
Remove-Item Env:RUN_OLLAMA_INTEGRATION_TESTS -ErrorAction SilentlyContinue
```

### Test coverage

The suite includes unit tests for domain validation, webhook verification and
routing, installation and pull-request event handling, GitHub API adapters,
provider adapters, job retries and leases, standards retrieval, and persistence.

Integration tests cover PostgreSQL job queue behavior, review-result persistence,
standard embeddings, GitHub installation lookup, and optional real Ollama calls.

## Verify a live pull-request flow

1. Confirm `/health` responds with `{"status":"ok"}`.
2. Keep PostgreSQL, Ollama, the API, worker, and HTTPS tunnel running.
3. Open a PR in a repository owned by the configured organization.
4. In GitHub App settings, inspect **Advanced → Recent deliveries**.
5. A successful webhook response is HTTP 200 with `{"status":"accepted"}`.
6. Check PostgreSQL for job status and findings:

```sql
SELECT j.organization_id, j.repository_id, j.pull_request_number,
       j.status, j.attempt_count, j.last_error,
       r.changed_files, r.analyzed_files,
       COUNT(f.id) AS finding_count
FROM review_jobs AS j
LEFT JOIN reviews AS r ON r.job_id = j.id
LEFT JOIN review_findings AS f ON f.review_id = r.id
GROUP BY j.id, r.id
ORDER BY j.created_at DESC;
```

A `completed` job means analysis and persistence completed. A `failed` job has an
error in `last_error`; `pending` or `processing` means it is waiting or running.

## Current limitations

- Findings are persisted, but the app does not yet publish review comments to GitHub.
- Only changed C# (`.cs`) files are analyzed.
- Pull requests from repositories not owned by an organization are rejected.
- The demo standards JSON has no implemented import/index command yet.
- Live Ollama tests require locally installed models and can be slower or
  nondeterministic compared with mocked unit tests.