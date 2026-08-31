"""意图槽位提取检查（spec 槽位测试清单）。"""

from medicalrag_core.intent.slot import (
    SlotDefinition,
    SlotSchema,
    SlotType,
    extract_slots,
)


def _schema() -> SlotSchema:
    return SlotSchema(
        slots=(
            SlotDefinition(
                "department", SlotType.ENUM, required=True, enum_values=("心内科", "呼吸科")
            ),
            SlotDefinition("age_group", SlotType.ENUM, enum_values=("成人", "儿童")),
            SlotDefinition("bed_count", SlotType.INTEGER, required=True),
            SlotDefinition("note", SlotType.STRING),
        )
    )


def test_valid_input_fills_values_and_is_complete():
    filling = extract_slots(
        _schema(), {"department": "心内科", "age_group": "儿童", "bed_count": "12", "note": "复诊"}
    )
    assert not filling.missing
    assert not filling.invalid
    assert filling.values == {
        "department": "心内科",
        "age_group": "儿童",
        "bed_count": 12,
        "note": "复诊",
    }


def test_missing_required_slot_reported():
    filling = extract_slots(_schema(), {"bed_count": 3})
    assert "department" in filling.missing
    assert filling.values == {"bed_count": 3}


def test_optional_slot_missing_is_not_reported():
    filling = extract_slots(_schema(), {"department": "心内科", "bed_count": 3})
    assert "age_group" not in filling.missing


def test_enum_violation_marks_invalid():
    filling = extract_slots(_schema(), {"department": "骨科", "bed_count": 3})
    assert filling.invalid == {"department": "骨科"}


def test_integer_is_coerced_from_digit_string():
    filling = extract_slots(_schema(), {"department": "心内科", "bed_count": "24"})
    assert filling.values["bed_count"] == 24
    assert isinstance(filling.values["bed_count"], int)


def test_invalid_integer_marked_invalid():
    filling = extract_slots(_schema(), {"department": "心内科", "bed_count": "多"})
    assert filling.invalid == {"bed_count": "多"}


def test_empty_string_is_invalid_for_string_slot():
    filling = extract_slots(_schema(), {"department": "心内科", "bed_count": 3, "note": ""})
    assert "note" in filling.invalid


def test_unknown_keys_are_ignored():
    filling = extract_slots(_schema(), {"department": "心内科", "bed_count": 3, "extra": "x"})
    assert "extra" not in filling.values
