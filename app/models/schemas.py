"""Pydantic-схемы: входной JSON прибора, карточка товара и ответ API."""
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

# Требования к формату карточки
SEO_TITLE_MAX_LENGTH = 70

# Маркер отсутствующих данных (требование заказчика): если характеристика
# отсутствует или пуста, в карточке должно быть указано именно это значение.
NO_DATA_MARKER = "данных нет"
SEO_DESCRIPTION_MIN_LENGTH = 800
SEO_DESCRIPTION_MAX_LENGTH = 1200
SEARCH_QUERIES_MIN = 3
SEARCH_QUERIES_MAX = 5

OutputFormat = Literal["json", "markdown", "text"]


class DeviceSpecs(BaseModel):
    """Характеристики прибора — произвольный набор пар ключ/значение.

    Пример:
        {"диапазон измерений": "0–1,6 МПа", "класс точности": "1,5"}
    """

    model_config = {"extra": "allow"}

    def to_kv(self) -> dict[str, Any]:
        """Вернуть сырой словарь характеристик (включая None-значения)."""
        return self.model_dump()


class DeviceInput(BaseModel):
    """Входные данные с веб-формы / JSON-запроса."""

    name: str = Field(..., min_length=1, examples=["Манометр показывающий DM 02"])
    manufacturer: str = Field(..., min_length=1, examples=["Манотомь"])
    specs: DeviceSpecs = Field(default_factory=DeviceSpecs)
    description: str = Field("", examples=["Прибор предназначен для измерения избыточного давления..."])

    @field_validator("name", "manufacturer")
    @classmethod
    def reject_blank(cls, value: str, info: ValidationInfo) -> str:
        """Запретить пустые/состоящие из пробелов обязательные поля."""
        stripped = value.strip()
        if not stripped:
            raise ValueError(
                f"Поле '{info.field_name}' не может быть пустым или состоять из пробелов"
            )
        return stripped


class GenerateRequest(BaseModel):
    """Тело запроса к /api/generate."""

    device: DeviceInput
    output_format: OutputFormat = "json"


class SpecItem(BaseModel):
    """Одна пара «параметр — значение» из списка характеристик."""

    key: str
    value: str


class CardContent(BaseModel):
    """Структурированная карточка товара, которую возвращает LLM.

    Обязательные разделы:
    - seo_title       — SEO-заголовок до 70 символов;
    - seo_description — SEO-описание 800–1 200 символов;
    - specs           — структурированный список ключевых характеристик;
    - search_queries  — 3–5 поисковых запросов для оптимизации страницы;
    - commercial_block— краткий commercial-блок для менеджера;
    - missing_fields  — поля входных данных, которых не хватило или которые
                        требуют уточнения.
    """

    seo_title: str
    seo_description: str
    specs: list[SpecItem] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    commercial_block: str
    missing_fields: list[str] = Field(default_factory=list)

    @field_validator("seo_title")
    @classmethod
    def truncate_title(cls, value: str) -> str:
        """Гарантировать SEO-заголовок не длиннее 70 символов."""
        return value.strip()[:SEO_TITLE_MAX_LENGTH].strip()

    @field_validator("seo_description", "commercial_block")
    @classmethod
    def strip_text(cls, value: str) -> str:
        """Убрать лишние пробелы вокруг текста."""
        return value.strip()

    @field_validator("search_queries")
    @classmethod
    def clamp_queries(cls, value: list[str]) -> list[str]:
        """Оставить не более 5 запросов, убрать пустые элементы."""
        cleaned = [q.strip() for q in value if q.strip()]
        return cleaned[:SEARCH_QUERIES_MAX]

    def validation_warnings(self) -> list[str]:
        """Неблокирующие предупреждения о несоответствии требованиям."""
        warnings: list[str] = []
        desc_len = len(self.seo_description)
        if desc_len < SEO_DESCRIPTION_MIN_LENGTH:
            warnings.append(
                f"SEO-описание короче минимума: {desc_len} симв. (требуется "
                f"{SEO_DESCRIPTION_MIN_LENGTH}–{SEO_DESCRIPTION_MAX_LENGTH})"
            )
        elif desc_len > SEO_DESCRIPTION_MAX_LENGTH:
            warnings.append(
                f"SEO-описание длиннее максимума: {desc_len} симв. (требуется "
                f"{SEO_DESCRIPTION_MIN_LENGTH}–{SEO_DESCRIPTION_MAX_LENGTH})"
            )
        if len(self.search_queries) < SEARCH_QUERIES_MIN:
            warnings.append(
                f"Поисковых запросов меньше {SEARCH_QUERIES_MIN}: получено {len(self.search_queries)}"
            )
        if not self.specs:
            warnings.append("Список ключевых характеристик пуст")
        return warnings


class GenerateResponse(BaseModel):
    """Ответ API с готовой карточкой."""

    name: str
    output_format: OutputFormat
    content: str  # готовая карточка (JSON-строка, Markdown или plain text)
    missing_fields: list[str] = Field(default_factory=list)  # чего не хватило во входных данных
    warnings: list[str] = Field(default_factory=list)  # несоответствия требованиям формата
    model: str  # какая модель GigaChat использовалась


class ErrorResponse(BaseModel):
    """Стандартная ошибка API."""

    detail: str
