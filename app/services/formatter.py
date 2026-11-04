"""Выходной форматтер: приводит ответ модели к карточке и целевому виду.

Модель всегда возвращает JSON по схеме карточки; здесь он:
1. парсится и валидируется в :class:`CardContent`;
2. рендерится в запрошенный формат — JSON, Markdown или plain text.
"""
import json
import logging
import re
from collections.abc import Callable

from pydantic import ValidationError

from app.models.schemas import NO_DATA_MARKER, CardContent, OutputFormat

logger = logging.getLogger(__name__)


class FormatterError(Exception):
    """Ошибка при форматировании ответа модели."""


def parse_card(raw: str) -> CardContent:
    """Распарсить «сырой» ответ модели в структурированную карточку.

    Пробуем по очереди: очищенный от markdown-обёрток текст и первый
    извлечённый из него JSON-объект (на случай «приписок» модели вокруг JSON).

    :param raw: текст, сгенерированный LLM (ожидается JSON).
    :raises FormatterError: если ответ не является валидным JSON-карточкой.
    """
    cleaned = _strip_code_fences(raw)
    # dict.fromkeys — дедупликация с сохранением порядка: когда cleaned сам
    # является JSON-объектом, оба кандидата совпадают и валидируется один.
    candidates = dict.fromkeys((cleaned, _extract_json_object(cleaned)))
    last_error: ValidationError | None = None
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            return CardContent.model_validate_json(candidate)
        except ValidationError as exc:
            last_error = exc
            logger.warning("Кандидат JSON не прошёл валидацию схемы: %s", exc)
    logger.error("Ответ модели не является валидной карточкой: %s", last_error)
    raise FormatterError(f"Ответ модели не является валидной карточкой: {last_error}")


def format_response(card: CardContent, output_format: OutputFormat) -> str:
    """Привести карточку к целевому формату вывода.

    :param card: структурированная карточка товара.
    :param output_format: 'json' | 'markdown' | 'text'.
    :raises FormatterError: если формат неизвестен или рендер дал пустой результат.
    """
    renderer = _RENDERERS.get(output_format)
    if renderer is None:
        raise FormatterError(f"Неизвестный формат вывода: {output_format}")
    rendered = renderer(card)
    if not rendered.strip():
        raise FormatterError("Рендер карточки дал пустой результат")
    return rendered


def _extract_json_object(text: str) -> str | None:
    """Найти в тексте первый распарсиваемый JSON-объект { ... }.

    Использует :meth:`json.JSONDecoder.raw_decode` вместо жадной регекспы:
    корректно обрабатывает фигурные скобки внутри строк и мусор вокруг JSON.
    """
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            _, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        return text[start:end]
    return None


def _strip_code_fences(text: str) -> str:
    """Убрать ```json ... ``` обёртки, которые любит добавлять LLM."""
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


def _escape_md_cell(value: str) -> str:
    """Экранировать значение для ячейки Markdown-таблицы."""
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _render_markdown(card: CardContent) -> str:
    """Собрать карточку в Markdown, удобном для копирования."""
    lines: list[str] = [
        f"# {card.seo_title}",
        "",
        "## SEO-описание",
        card.seo_description,
        "",
        "## Ключевые характеристики",
        "",
        "| Параметр | Значение |",
        "|---|---|",
    ]
    if card.specs:
        lines.extend(
            f"| {_escape_md_cell(spec.key)} | {_escape_md_cell(spec.value)} |"
            for spec in card.specs
        )
    else:
        lines.append(f"| Характеристики | {NO_DATA_MARKER} |")

    lines += ["", "## Поисковые запросы", ""]
    lines.extend(f"{i}. {query}" for i, query in enumerate(card.search_queries, start=1))

    lines += ["", "## Коммерческий блок", card.commercial_block]

    if card.missing_fields:
        lines += ["", "## ⚠️ Требуется уточнить", ""]
        lines.extend(f"- {field}" for field in card.missing_fields)

    return "\n".join(lines).strip()


def _render_text(card: CardContent) -> str:
    """Собрать карточку в виде простого текста без разметки."""
    lines: list[str] = [
        f"SEO-ЗАГОЛОВОК: {card.seo_title}",
        "",
        "SEO-ОПИСАНИЕ:",
        card.seo_description,
        "",
        "КЛЮЧЕВЫЕ ХАРАКТЕРИСТИКИ:",
    ]
    if card.specs:
        lines.extend(f"  {spec.key}: {spec.value}" for spec in card.specs)
    else:
        lines.append(f"  {NO_DATA_MARKER}")

    lines += ["", "ПОИСКОВЫЕ ЗАПРОСЫ:"]
    lines.extend(f"  {i}. {query}" for i, query in enumerate(card.search_queries, start=1))

    lines += ["", "КОММЕРЧЕСКИЙ БЛОК:", card.commercial_block]

    if card.missing_fields:
        lines += ["", "ТРЕБУЕТСЯ УТОЧНИТЬ:"]
        lines.extend(f"  - {field}" for field in card.missing_fields)

    return "\n".join(lines).strip()


def _render_json(card: CardContent) -> str:
    """Собрать карточку в виде JSON-строки (без None-полей)."""
    return card.model_dump_json(indent=2, exclude_none=True)


# Таблица рендеров: добавление нового формата — новая функция + одна строка здесь.
_RENDERERS: dict[OutputFormat, Callable[[CardContent], str]] = {
    "json": _render_json,
    "markdown": _render_markdown,
    "text": _render_text,
}
