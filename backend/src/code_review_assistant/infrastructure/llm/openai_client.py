from openai import AsyncOpenAI

from code_review_assistant.settings import Settings


def create_openai_client(settings: Settings) -> AsyncOpenAI:
    if settings.openai_api_key is None:
        raise RuntimeError("OPENAI_API_KEY must be configured to use OpenAI")

    return AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=30.0,
        max_retries=2,
    )