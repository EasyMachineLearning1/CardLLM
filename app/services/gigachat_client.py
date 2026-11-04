"""Асинхронная обёртка над официальным GigaChat SDK.

SDK сам управляет получением и обновлением access-токена по ключу авторизации.
Клиент полностью асинхронный (``GigaChatAsyncClient`` + ``await``), поэтому
длительный запрос к модели НЕ блокирует event loop сервера.

Разделение ответственности:
- :meth:`GigaChatClient.generate` — публичный API клиента;
- :meth:`GigaChatClient._build_chat` — формирование запроса к модели;
- :meth:`GigaChatClient._generate_with_retries` — политика повторных попыток;
- :meth:`GigaChatClient._request_content` — одиночный вызов API + извлечение текста;
- :meth:`GigaChatClient._wait_before_retry` — экспоненциальная задержка между попытками.

Обработка ошибок API (требование заказчика):
- ошибки GigaChat SDK превращаются в понятное исключение GigaChatAPIError;
- временные сбои (лимит запросов, ошибка сервера, сеть/таймаут) ретраются
  с экспоненциальной задержкой (``asyncio.sleep`` — без блокировки потока);
- пустой ответ модели (нет choices или пустой контент) считается ошибкой
  и тоже ретрается.
"""
import asyncio
import logging

import httpx
from gigachat import GigaChatAsyncClient
from gigachat.exceptions import GigaChatException, RateLimitError, ServerError
from gigachat.models import Chat, ChatCompletion, Messages

from app.config import Settings

logger = logging.getLogger(__name__)

# Временные сбои, которые имеет смысл повторить. httpx.TransportError покрывает
# сетевые ошибки и таймауты, но не проблемы SSL-сертификатов и прочие
# неисправимые ошибки выше по иерархии httpx.HTTPError.
RETRYABLE_ERRORS = (RateLimitError, ServerError, httpx.TransportError)


class GigaChatAPIError(Exception):
    """Пользовательская ошибка обращения к GigaChat API."""


class _EmptyResponseError(Exception):
    """Внутренний маркер: модель вернула ответ без полезного контента."""


def _extract_content(response: ChatCompletion) -> str:
    """Извлечь текст ответа модели; пустой ответ — ошибка, а не None."""
    if not response.choices:
        raise _EmptyResponseError("в ответе отсутствуют choices")
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise _EmptyResponseError("модель вернула пустой ответ")
    return content


class GigaChatClient:
    """Клиент для генерации текста через GigaChat (async)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = GigaChatAsyncClient(
            credentials=settings.gigachat_credentials,
            scope=settings.gigachat_scope,
            verify_ssl_certs=settings.gigachat_verify_ssl,
            timeout=settings.gigachat_timeout,
        )

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Отправить запрос в GigaChat и вернуть текст ответа.

        :param prompt: пользовательский промпт (данные прибора + задание).
        :param system_prompt: системная инструкция (роль и формат ответа).
        :raises GigaChatAPIError: при ошибке API или пустом ответе модели.
        """
        chat = self._build_chat(prompt, system_prompt)
        logger.info("Запрос в GigaChat: model=%s, prompt_len=%d", chat.model, len(prompt))

        content = await self._generate_with_retries(chat)
        logger.info("Ответ GigaChat получен: %d символов", len(content))
        return content

    def _build_chat(self, prompt: str, system_prompt: str | None) -> Chat:
        """Собрать payload запроса из промпта и настроек модели."""
        messages: list[Messages] = []
        if system_prompt:
            messages.append(Messages(role="system", content=system_prompt))
        messages.append(Messages(role="user", content=prompt))
        return Chat(
            messages=messages,
            model=self.settings.gigachat_model,
            temperature=self.settings.gigachat_temperature,
        )

    async def _generate_with_retries(self, chat: Chat) -> str:
        """Политика ретраев: временные сбои и пустые ответы — с экспоненциальной задержкой.

        Неисправимые ошибки (неверный ключ, bad request и т.п.) не ретраются.
        """
        attempts = max(1, self.settings.gigachat_max_retries)
        for attempt in range(1, attempts + 1):
            try:
                return await self._request_content(chat)
            except RETRYABLE_ERRORS as exc:
                reason: Exception = exc
            except _EmptyResponseError as exc:
                reason = exc
            except GigaChatException as exc:
                raise GigaChatAPIError(f"Ошибка GigaChat API: {exc}") from exc

            if attempt == attempts:
                raise GigaChatAPIError(
                    f"GigaChat недоступен после {attempts} попыток: {reason}"
                ) from reason
            await self._wait_before_retry(attempt, attempts, reason)

        raise GigaChatAPIError("GigaChat недоступен: попытки исчерпаны")  # pragma: no cover

    async def _request_content(self, chat: Chat) -> str:
        """Один вызов API и извлечение текста ответа модели."""
        response = await self._client.achat(chat)
        return _extract_content(response)

    async def _wait_before_retry(self, attempt: int, attempts: int, reason: Exception) -> None:
        """Экспоненциальная задержка перед следующей попыткой (не блокирует поток)."""
        delay = self.settings.gigachat_retry_delay * (2 ** (attempt - 1))
        logger.warning(
            "Попытка %d/%d не удалась (%s), повтор через %.1f с",
            attempt, attempts, reason, delay,
        )
        await asyncio.sleep(delay)

    async def aclose(self) -> None:
        """Освободить ресурсы клиента."""
        await self._client.aclose()
