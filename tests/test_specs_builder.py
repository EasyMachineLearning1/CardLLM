"""Тесты детерминированного построения характеристик (specs_builder)."""
from app.models.schemas import NO_DATA_MARKER, DeviceInput, DeviceSpecs
from app.services.specs_builder import build_specs


def _device(specs: dict) -> DeviceInput:
    return DeviceInput(name="Манометр DM 02", manufacturer="Манотомь", specs=DeviceSpecs.model_validate(specs))


def test_string_value_kept_as_is() -> None:
    result = build_specs(_device({"диапазон": " 0–1,6 МПа "}))
    assert result[0].value == "0–1,6 МПа"


def test_none_and_empty_become_no_data_marker() -> None:
    result = build_specs(_device({"a": None, "b": "", "c": "   ", "d": [], "e": {}}))
    assert all(item.value == NO_DATA_MARKER for item in result)


def test_bool_becomes_da_net() -> None:
    result = build_specs(_device({"взрывозащищённый": True, "резервный": False}))
    assert [item.value for item in result] == ["да", "нет"]


def test_numbers_stringified() -> None:
    result = build_specs(_device({"класс точности": 1.5, "диаметр": 100}))
    assert [item.value for item in result] == ["1.5", "100"]


def test_nested_containers_serialized_to_json() -> None:
    result = build_specs(_device({"опции": ["сигнализация", "клапан"]}))
    assert result[0].value == '["сигнализация", "клапан"]'


def test_blank_key_gets_placeholder_name() -> None:
    result = build_specs(_device({"  ": "значение"}))
    assert result[0].key == "Без названия"


def test_specs_order_preserved() -> None:
    result = build_specs(_device({"b": "2", "a": "1"}))
    assert [item.key for item in result] == ["b", "a"]
