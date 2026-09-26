from __future__ import annotations

from app.agents.providers.base import LLMProvider, ProviderUnavailable
from app.agents.providers.mock_provider import MockProvider
from app.core.config import Settings

# Known base URLs for named OpenAI-compatible providers. "custom" has no
# entry here on purpose — it always requires LLM_API_BASE to be set
# explicitly, since there's no default to guess for an arbitrary endpoint.
#
# "groq" is worth its own entry because its base URL ends in /openai/v1
# rather than /v1 like OpenAI's, and because getting it wrong produces a
# confusing 404 rather than an obvious error.
PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "grok": "https://api.x.ai/v1",
    "deepseek": "https://api.deepseek.com",
    "groq": "https://api.groq.com/openai/v1",
}

PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    "openai": "OpenAI",
    "grok": "Grok (xAI)",
    "deepseek": "DeepSeek",
    "groq": "Groq",
    "anthropic": "Claude",
    "custom": "Custom provider",
}


def _build_one(
    *,
    provider_name: str,
    model: str | None,
    api_key: str | None,
    api_base: str | None,
    temperature: float,
) -> LLMProvider:
    """Construct one provider, or return None when it is not configured.

    A provider that cannot possibly work — a named provider with no API
    key, or "custom" with no base URL — is skipped rather than raised on,
    so one missing key in the fallback slot cannot take down the whole app.
    """
    if provider_name == "mock":
        return MockProvider()

    if not api_key:
        return None

    model_id = model or ""

    if provider_name == "anthropic":
        from app.agents.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=api_key,
            model=model_id,
            temperature=temperature,
            base_url=api_base,
        )

    # openai / grok / groq / deepseek / custom all speak the same
    # OpenAI-compatible Chat Completions API.
    from app.agents.providers.openai_compatible_provider import OpenAICompatibleProvider

    base_url = api_base or PROVIDER_BASE_URLS.get(provider_name)
    if not base_url:
        # "custom" without a base URL: nothing to guess, so refuse.
        return None

    return OpenAICompatibleProvider(
        api_key=api_key,
        model=model_id,
        base_url=base_url,
        display_name=PROVIDER_DISPLAY_NAMES.get(provider_name, provider_name.title()),
        temperature=temperature,
    )


def get_llm_provider(settings: Settings) -> LLMProvider:
    """Build the provider chain from configuration.

    A single configured provider still returns that provider directly
    rather than a one-element chain, so the trace and the behaviour are
    unchanged for everyone not using a fallback.
    """
    primary = _build_one(
        provider_name=settings.llm_provider,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        api_base=settings.llm_api_base,
        temperature=settings.llm_temperature,
    )
    if primary is None:
        raise ProviderUnavailable(
            f"Provider {settings.llm_provider!r} is not usable: set LLM_API_KEY "
            f"(and LLM_API_BASE when LLM_PROVIDER=custom)"
        )

    if not settings.has_llm_fallback:
        return primary

    fallback = _build_one(
        provider_name=settings.llm_fallback_provider,
        model=settings.llm_fallback_model or settings.llm_model,
        # A fallback slot with no key of its own reuses the primary key.
        # Convenient when both providers are reached with one credential,
        # and ignored (the slot is simply skipped) when they are not.
        api_key=settings.llm_fallback_api_key or settings.llm_api_key,
        api_base=settings.llm_fallback_api_base,
        temperature=settings.llm_temperature,
    )
    if fallback is None:
        return primary

    from app.agents.providers.fallback_provider import FallbackProvider

    return FallbackProvider([primary, fallback])
