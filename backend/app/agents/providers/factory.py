from __future__ import annotations

from app.agents.providers.base import LLMProvider
from app.agents.providers.mock_provider import MockProvider
from app.core.config import Settings


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "anthropic":
        from app.agents.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=settings.llm_api_key or "",
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            base_url=settings.llm_api_base,
        )
    return MockProvider()
