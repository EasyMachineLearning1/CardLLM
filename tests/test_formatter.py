"""Тесты разбора и рендера ответа модели (formatter)."""
import pytest

from app.models.schemas import CardContent, SpecItem
from app.services.formatter import FormatterError, format_response, parse_card

VALID_CARD = {
    "seo_title": "Манометр показывающий DM 02 для измерения давления",
    "seo_description": "Прибор предназначен для измерения избыточного давления.",
    "commercial_block": "Подходит для котельных и насосных станций.",
}


def _make_card(**overrides) -> CardContent:
    return CardContent.model_validate({**VALID_CARD, **overrides})


class TestParseCard:
    def test_plain_json(self) -> None:
        card = parse_card('{"seo_title": "T", "seo_description": "D", "commercial_block": "C"}')
        assert card.seo_title == "T"
        assert card.commercial_block == "C"

    def test_json_in_code_fence(self) -> None:
        raw = "```json\n" + '{"seo_title": "T", "seo_description": "D", "commercial_block": "C"}\n```'
        assert parse_card(raw).seo_title == "T"

    def test_json_with_text_around(self) -> None:
        raw = 'Вот карточка: {"seo_title": "T", "seo_description": "D", "commercial_block": "C"} удачи!'
        assert parse_card(raw).seo_title == "T"

    def test_broken_json_raises(self) -> None:
        with pytest.raises(FormatterError):
            parse_card("{не json вовсе")

    def test_json_not_matching_schema_raises(self) -> None:
        with pytest.raises(FormatterError):
            parse_card('{"unexpected_field": 1}')

    def test_empty_input_raises(self) -> None:
        with pytest.raises(FormatterError):
            parse_card("   ")


class TestFormatResponse:
    def test_json_format(self) -> None:
        card = _make_card()
        content = format_response(card, "json")
        assert '"seo_title"' in content

    def test_text_format(self) -> None:
        card = _make_card(specs=[SpecItem(key="класс точности", value="1.5")])
        content = format_response(card, "text")
        assert "класс точности: 1.5" in content

    def test_markdown_escapes_table_cells(self) -> None:
        """Значения с '|' и переносами строк не ломают Markdown-таблицу."""
        card = _make_card(specs=[SpecItem(key="диапазон | измерений", value="0–1,6 МПа\nкласс 1")])
        content = format_response(card, "markdown")
        assert "| диапазон \\| измерений | 0–1,6 МПа класс 1 |" in content

    def test_markdown_without_specs(self) -> None:
        card = _make_card()
        content = format_response(card, "markdown")
        assert "| Характеристики | данных нет |" in content
