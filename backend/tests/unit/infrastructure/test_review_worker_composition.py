from pathlib import Path
from unittest.mock import Mock, patch

from code_review_assistant.application.services.review_job_worker import (
    ReviewJobWorker,
)
from code_review_assistant.infrastructure.review_worker_composition import (
    create_review_job_worker,
)
from code_review_assistant.settings import Settings


def test_ollama_composition_does_not_require_paid_provider_clients() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        github_app_id=123,
        github_private_key_path=Path("test-github-app.pem"),
        review_provider="ollama",
        review_model="llama3.2:latest",
        embedding_provider="ollama",
        embedding_model="nomic-embed-text:latest",
        embedding_dimensions=768,
        ollama_base_url="http://127.0.0.1:11434",
    )

    github_client = Mock()
    ollama_client = Mock()
    session_factory = Mock()

    with (
        patch(
            "code_review_assistant.infrastructure.review_worker_composition.OllamaReviewAnalyzer"
        ) as review_analyzer,
        patch(
            "code_review_assistant.infrastructure.review_worker_composition.OllamaTextEmbedder"
        ) as text_embedder,
        patch(
            "code_review_assistant.infrastructure.review_worker_composition.AnthropicReviewAnalyzer"
        ) as anthropic_analyzer,
        patch(
            "code_review_assistant.infrastructure.review_worker_composition.OpenAITextEmbedder"
        ) as openai_embedder,
    ):
        worker = create_review_job_worker(
            settings,
            session_factory,
            github_client,
            ollama_http_client=ollama_client,
        )

    assert isinstance(worker, ReviewJobWorker)
    review_analyzer.assert_called_once_with(
        ollama_client,
        "http://127.0.0.1:11434",
        "llama3.2:latest",
    )
    text_embedder.assert_called_once_with(
        ollama_client,
        "http://127.0.0.1:11434",
        "nomic-embed-text:latest",
        768,
    )
    anthropic_analyzer.assert_not_called()
    openai_embedder.assert_not_called()