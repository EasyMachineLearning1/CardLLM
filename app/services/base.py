"""Абстракции зависимостей (DIP): верхние слои не зависят от конкретного SDK.

Оркестратор (:class:`app.services.card_service.CardGenerationService`) принимает
любой объект, удовлетворяющий :class:`TextGenerator`, — реальный
:class:`app.services.gigachat_client.GigaChatClient` или фейк в тестах.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class TextGenerator(Protocol):
    """Протокол генератора текста (async)."""

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Вернуть текст, сгенерированный моделью, или выбросить GigaChatAPIError."""
        ...

    async def aclose(self) -> None:
        """Освободить ресурсы генератора."""
        ...
