from code_review_assistant.infrastructure.llm.ollama_review_analyzer import OllamaReviewAnalyzer
from code_review_assistant.infrastructure.llm.ollama_text_embedder import OllamaTextEmbedder
import httpx
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from code_review_assistant.application.services.process_review_job import (
    ProcessReviewJob,
)
from code_review_assistant.application.services.retrieve_relevant_standards import (
    RetrieveRelevantStandards,
)
from code_review_assistant.application.services.review_job_worker import (
    ReviewJobWorker,
)
from code_review_assistant.application.services.review_pull_request import (
    ReviewPullRequest,
)
from code_review_assistant.infrastructure.database.github_installation_reader import (
    SqlAlchemyGitHubInstallationReader,
)
from code_review_assistant.infrastructure.database.review_job_queue import (
    SqlAlchemyReviewJobQueue,
)
from code_review_assistant.infrastructure.database.review_result_writer import (
    SqlAlchemyReviewResultWriter,
)
from code_review_assistant.infrastructure.database.standard_embedding_store import (
    SqlAlchemyStandardEmbeddingStore,
)
from code_review_assistant.infrastructure.github_app_token_provider import (
    GitHubAppTokenProvider,
)
from code_review_assistant.infrastructure.github_pull_request_reader import (
    GitHubPullRequestReader,
)
from code_review_assistant.infrastructure.llm.anthropic_review_analyzer import (
    AnthropicReviewAnalyzer,
)
from code_review_assistant.infrastructure.llm.openai_text_embedder import (
    OpenAITextEmbedder,
)
from code_review_assistant.settings import Settings


def create_review_job_worker(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    github_http_client: httpx.AsyncClient,
    anthropic_client: AsyncAnthropic | None = None,
    openai_client: AsyncOpenAI | None = None,
    ollama_http_client: httpx.AsyncClient | None = None,
) -> ReviewJobWorker:
    if settings.github_app_id is None:
        raise RuntimeError("GITHUB_APP_ID must be configured")
    if settings.github_private_key_path is None:
        raise RuntimeError("GITHUB_PRIVATE_KEY_PATH must be configured")
   
    if settings.embedding_provider == "ollama":
        if ollama_http_client is None:
            raise RuntimeError("An HTTP client is required for Ollama embeddings")
        if settings.embedding_model is None:
            raise RuntimeError("EMBEDDING_MODEL must be configured for Ollama")
        embedder = OllamaTextEmbedder(
            ollama_http_client,
            settings.ollama_base_url,
            settings.embedding_model,
            settings.embedding_dimensions,
        )
    else:
        if openai_client is None:
            raise RuntimeError("An OpenAI client is required for OpenAI embeddings")
        if (
            settings.embedding_model is not None
            and settings.embedding_model != "text-embedding-3-small"
        ):
            raise RuntimeError(
                "OpenAI embeddings currently support only text-embedding-3-small"
            )
        if settings.embedding_dimensions != 1536:
            raise RuntimeError(
                "text-embedding-3-small requires 1536 embedding dimensions"
            )
        embedder = OpenAITextEmbedder(openai_client)

    installation_reader = SqlAlchemyGitHubInstallationReader(session_factory)
    token_provider = GitHubAppTokenProvider(settings, github_http_client)
    pull_request_reader = GitHubPullRequestReader(
        github_http_client,
        installation_reader,
        token_provider,
    )

    standards_reader = RetrieveRelevantStandards(
        SqlAlchemyStandardEmbeddingStore(session_factory),
        embedder,
    )

    if settings.review_provider == "ollama":
        if ollama_http_client is None:
            raise RuntimeError("An HTTP client is required for Ollama review")
        if settings.review_model is None:
            raise RuntimeError("REVIEW_MODEL must be configured for Ollama")

        analyzer = OllamaReviewAnalyzer(
            ollama_http_client,
            settings.ollama_base_url,
            settings.review_model,
        )
    else:
        if anthropic_client is None:
            raise RuntimeError("An Anthropic client is required for review analysis")

        model = settings.review_model or settings.anthropic_model
        if model is None:
            raise RuntimeError(
                "REVIEW_MODEL or ANTHROPIC_MODEL must be configured for Anthropic"
            )

        analyzer = AnthropicReviewAnalyzer(anthropic_client, model)

    review = ReviewPullRequest(pull_request_reader, standards_reader, analyzer)

    processor = ProcessReviewJob(
        SqlAlchemyReviewJobQueue(session_factory),
        review,
        SqlAlchemyReviewResultWriter(session_factory),
    )
    return ReviewJobWorker(processor)

