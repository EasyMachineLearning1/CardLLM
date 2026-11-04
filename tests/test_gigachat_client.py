"""Тесты клиента GigaChat: политика ретраев и сборка запроса (стаб вместо SDK)."""
import asyncio
from types import SimpleNamespace

import pytest
from gigachat.exceptions import GigaChatException

from app.config import Settings
from app.services.gigachat_client import GigaChatAPIError, GigaChatClient


class _StubAsyncClient:
    """Стаб асинхронного клиента: выдаёт заготовленные результаты/исключения по очереди."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    async def achat(self, chat):
        self.calls += 1
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FatalError(GigaChatException):
    """Неисправимая ошибка API (например, неверный ключ)."""


def _ok_response(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _empty_response():
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=""))])


def _make_client(results) -> GigaChatClient:
    settings = Settings(
        _env_file=None,
        gigachat_credentials="test-key",
        gigachat_max_retries=3,
        gigachat_retry_delay=0,
    )
    client = GigaChatClient(settings)
    client._client = _StubAsyncClient(results)
    return client


class TestGenerateRetries:
    def test_empty_response_is_retried_and_then_succeeds(self) -> None:
        client = _make_client([_empty_response(), _ok_response("готово")])
        result = asyncio.run(client.generate("промпт"))
        assert result == "готово"

    def test_empty_response_raises_after_all_attempts(self) -> None:
        client = _make_client([_empty_response()] * 3)
        with pytest.raises(GigaChatAPIError, match="после 3 попыток"):
            asyncio.run(client.generate("промпт"))

    def test_fatal_error_is_not_retried(self) -> None:
        client = _make_client([_FatalError("неверный ключ")])
        with pytest.raises(GigaChatAPIError):
            asyncio.run(client.generate("промпт"))
        assert client._client.calls == 1  # без ретраев

    def test_retryable_error_is_retried(self) -> None:
        import httpx

        client = _make_client([httpx.ConnectError("сеть недоступна"), _ok_response("ответ")])
        result = asyncio.run(client.generate("промпт"))
        assert result == "ответ"
        assert client._client.calls == 2


class TestBuildChat:
    def test_system_prompt_added_first(self) -> None:
        settings = Settings(_env_file=None, gigachat_credentials="test-key")
        client = GigaChatClient(settings)
        chat = client._build_chat("данные прибора", system_prompt="роль")
        assert len(chat.messages) == 2
        assert chat.messages[0].role == "system"
        assert chat.messages[0].content == "роль"
        assert chat.messages[1].role == "user"
        assert chat.messages[1].content == "данные прибора"

    def test_without_system_prompt(self) -> None:
        settings = Settings(_env_file=None, gigachat_credentials="test-key")
        client = GigaChatClient(settings)
        chat = client._build_chat("данные прибора", system_prompt=None)
        assert len(chat.messages) == 1
        assert chat.messages[0].role == "user"
