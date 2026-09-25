from __future__ import annotations

from app.agents.providers.base import LLMProvider, ProviderUnavailable
from app.agents.providers.mock_provider import MockProvider
from app.core.config import Settings

# Known base URLs for named OpenAI-compatible providers. "custom" has no
# entry here on purpose — it always requires LLM_API_BASE to be set
# explicitly, since there's no default to guess for an arbitrary endpoint.
PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "grok": "https://api.x.ai/v1",
    "deepseek": "https://api.deepseek.com",
}

PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    "openai": "OpenAI",
    "grok": "Grok (xAI)",
    "deepseek": "DeepSeek",
    "custom": "Custom provider",
}


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockProvider()

    if settings.llm_provider == "anthropic":
        from app.agents.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=settings.llm_api_key or "",
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            base_url=settings.llm_api_base,
        )

    # openai / grok / deepseek / custom all speak the same
    # OpenAI-compatible Chat Completions API.
    from app.agents.providers.openai_compatible_provider import OpenAICompatibleProvider

    base_url = settings.llm_api_base or PROVIDER_BASE_URLS.get(settings.llm_provider)
    if not base_url:
        raise ProviderUnavailable(
            f"LLM_API_BASE must be set when LLM_PROVIDER={settings.llm_provider!r}"
        )

    return OpenAICompatibleProvider(
        api_key=settings.llm_api_key or "",
        model=settings.llm_model,
        base_url=base_url,
        display_name=PROVIDER_DISPLAY_NAMES.get(settings.llm_provider, settings.llm_provider.title()),
        temperature=settings.llm_temperature,
    )
