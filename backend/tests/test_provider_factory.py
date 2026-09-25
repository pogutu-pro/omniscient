"""Provider selection is a pure config-to-implementation mapping — verified
here without any network calls, since the whole point of the abstraction
is that the rest of the app never needs to know which provider is active.
"""
from __future__ import annotations

import pytest

from app.agents.providers.factory import PROVIDER_BASE_URLS, get_llm_provider
from app.agents.providers.mock_provider import MockProvider
from app.agents.providers.openai_compatible_provider import OpenAICompatibleProvider
from app.core.config import Settings


def test_default_provider_is_mock_and_needs_no_key():
    settings = Settings()
    provider = get_llm_provider(settings)
    assert isinstance(provider, MockProvider)
    assert provider.display_name == "Mock Assistant"


@pytest.mark.parametrize("name", ["grok", "deepseek", "openai"])
def test_named_openai_compatible_providers_resolve_known_base_urls(name: str):
    settings = Settings(llm_provider=name, llm_api_key="test-key", llm_model="test-model")
    provider = get_llm_provider(settings)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert str(provider._client.base_url).rstrip("/") == PROVIDER_BASE_URLS[name].rstrip("/")


def test_grok_is_a_drop_in_swap_for_deepseek_via_config_only():
    grok = get_llm_provider(Settings(llm_provider="grok", llm_api_key="k", llm_model="grok-4-latest"))
    deepseek = get_llm_provider(Settings(llm_provider="deepseek", llm_api_key="k", llm_model="deepseek-chat"))
    assert type(grok) is type(deepseek) is OpenAICompatibleProvider
    assert grok.display_name == "Grok (xAI)"
    assert deepseek.display_name == "DeepSeek"


def test_custom_provider_requires_api_base_at_config_time():
    with pytest.raises(ValueError):
        Settings(llm_provider="custom", llm_api_key="k")


def test_custom_provider_uses_the_given_base_url():
    settings = Settings(
        llm_provider="custom", llm_api_key="k", llm_model="m", llm_api_base="https://llm.internal.example/v1"
    )
    provider = get_llm_provider(settings)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert "llm.internal.example" in str(provider._client.base_url)


def test_openai_compatible_provider_requires_an_api_key():
    from app.agents.providers.base import ProviderUnavailable

    with pytest.raises(ProviderUnavailable):
        OpenAICompatibleProvider(api_key="", model="m", base_url="https://example.com", display_name="Test")
