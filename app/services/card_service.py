"""Оркестрация генерации карточки: промпт -> модель -> разбор -> характеристики -> рендер.

Вынесено из эндпоинта (SRP): эндпоинт только принимает/отдаёт HTTP, здесь —
вся бизнес-логика. Зависимость от клиента инжектируется через абстракцию
:class:`app.services.base.TextGenerator` (DIP), что позволяет подменять её в тестах.
"""
import logging

from app.models.schemas import CardContent, GenerateRequest, GenerateResponse
from app.services.base import TextGenerator
from app.services.formatter import FormatterError, format_response, parse_card
from app.services.prompt_builder import RETRY_INSTRUCTION, SYSTEM_PROMPT, build_prompt, missing_input_hints
from app.services.specs_builder import build_specs

logger = logging.getLogger(__name__)


class CardGenerationService:
    """Сервис генерации карточек приборов."""

    def __init__(self, generator: TextGenerator, gigachat_model: str) -> None:
        self._generator = generator
        self._gigachat_model = gigachat_model

    async def generate_card(self, request: GenerateRequest) -> GenerateResponse:
        """Полный цикл генерации карточки по данным прибора.

        :raises GigaChatAPIError: при недоступности GigaChat API.
        :raises FormatterError: если модель дважды вернула невалидный ответ.
        """
        card = await self._request_card(request)
        # Характеристики — строго из входных данных (требование заказчика),
        # перезаписывают всё, что вернула модель. Пустые значения уже помечены
        # как «данных нет». Копия вместо мутации: карточка от модели остаётся
        # в исходном виде.
        card = card.model_copy(update={"specs": build_specs(request.device)})
        return self._assemble_response(request, card)

    async def _request_card(self, request: GenerateRequest) -> CardContent:
        """Промпт -> запрос к модели -> парсинг, с одной повторной попыткой."""
        prompt = build_prompt(request)
        raw = await self._generator.generate(prompt, system_prompt=SYSTEM_PROMPT)
        try:
            return parse_card(raw)
        except FormatterError:
            logger.warning("Ответ модели не разобран, повторная попытка с исправлением")
            raw_retry = await self._generator.generate(
                prompt + RETRY_INSTRUCTION, system_prompt=SYSTEM_PROMPT
            )
            return parse_card(raw_retry)  # второй неуспех — отдаём ошибку наружу

    def _assemble_response(self, request: GenerateRequest, card: CardContent) -> GenerateResponse:
        """Собрать HTTP-ответ из карточки и метаданных запроса."""
        return GenerateResponse(
            name=request.device.name,
            output_format=request.output_format,
            content=format_response(card, request.output_format),
            missing_fields=self._merge_missing_fields(request, card),
            warnings=card.validation_warnings(),
            model=self._gigachat_model,
        )

    @staticmethod
    def _merge_missing_fields(request: GenerateRequest, card: CardContent) -> list[str]:
        """Системные подсказки + находки модели; уникальность с сохранением порядка."""
        return list(dict.fromkeys([*missing_input_hints(request.device), *card.missing_fields]))
