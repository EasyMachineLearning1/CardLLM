"""Детерминированное построение списка характеристик из входных данных.

Ключевое требование заказчика: все технические значения в карточке должны
браться ТОЛЬКО из входных данных, модель не должна ничего выдумывать.
Поэтому характеристики не генерируются LLM, а собираются здесь, в коде:

- каждый параметр из ``device.specs`` попадает в карточку «как есть»;
- пустое/отсутствующее значение заменяется маркером «данных нет»;
- LLM не может добавить свои характеристики — они перезаписываются этим
  результатом после разбора ответа модели.
"""
import json
from typing import Any

from app.models.schemas import NO_DATA_MARKER, DeviceInput, SpecItem


def _stringify(value: Any) -> str:
    """Привести произвольное значение характеристики к строке без потерь."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, dict)) and not value:
        return ""  # пустой контейнер — данных нет
    # Непустые списки/словари — сериализуем в JSON, чтобы не потерять структуру.
    return json.dumps(value, ensure_ascii=False)


def build_specs(device: DeviceInput) -> list[SpecItem]:
    """Собрать характеристики строго из входных данных прибора.

    Пустые значения (None, пустая строка, пробелы, пустой контейнер)
    заменяются маркером :data:`NO_DATA_MARKER` («данных нет»).

    :param device: входные данные прибора.
    :returns: список пар «параметр — значение» для карточки.
    """
    items: list[SpecItem] = []
    for key, value in device.specs.to_kv().items():
        clean_key = str(key).strip() or "Без названия"
        text = _stringify(value)
        items.append(SpecItem(key=clean_key, value=text if text else NO_DATA_MARKER))
    return items
