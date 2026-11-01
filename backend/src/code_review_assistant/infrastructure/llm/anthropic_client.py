from anthropic import AsyncAnthropic

from code_review_assistant.settings import Settings


def create_anthropic_client(settings: Settings) -> AsyncAnthropic:
    if settings.anthropic_api_key is None:
        raise RuntimeError("ANTHROPIC_API_KEY must be configured to use Anthropic")

    return AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        timeout=30.0,
        max_retries=2,
    )