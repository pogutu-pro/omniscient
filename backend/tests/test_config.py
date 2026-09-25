from __future__ import annotations

from app.core.config import Settings


def test_database_ssl_and_cors_regex_default_off():
    settings = Settings()
    assert settings.database_ssl is False
    assert settings.cors_origin_regex is None


def test_neon_style_config_is_accepted():
    settings = Settings(
        database_url="postgresql+asyncpg://user:pw@ep-test-pooler.eu-west-1.aws.neon.tech/omniscient",
        database_ssl=True,
        cors_origin_regex=r"^https://omniscient(-[a-z0-9-]+)?\.vercel\.app$",
    )
    assert settings.database_ssl is True
    assert "neon.tech" in settings.database_url
    assert settings.cors_origin_regex is not None
