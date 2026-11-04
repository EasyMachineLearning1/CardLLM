"""Тесты fail-fast конфигурации."""
import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_require_credentials(monkeypatch) -> None:
    """Без GIGACHAT_CREDENTIALS приложение не должно стартовать."""
    monkeypatch.delenv("GIGACHAT_CREDENTIALS", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_verify_ssl_enabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("GIGACHAT_VERIFY_SSL", raising=False)
    monkeypatch.setenv("GIGACHAT_CREDENTIALS", "test-key")
    settings = Settings(_env_file=None)
    assert settings.gigachat_verify_ssl is True


def test_app_debug_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("APP_DEBUG", raising=False)
    monkeypatch.setenv("GIGACHAT_CREDENTIALS", "test-key")
    settings = Settings(_env_file=None)
    assert settings.app_debug is False
