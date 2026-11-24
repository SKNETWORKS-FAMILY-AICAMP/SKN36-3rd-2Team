"""Issue #147 - 서버 전용 Story Event Loader 검증."""

import json

import pytest

from crimescene.scenario.loaders.story_event_bindings_loader import (
    load_story_event_bindings,
)
from crimescene.scenario.loaders.story_event_conditions_loader import (
    load_story_event_conditions,
)

EVENT_KEY = "EVT-CH01-001"
STORY_ID = "STORY_001"


@pytest.fixture
def binding_data():
    return {
        "case_id": "CASE-001",
        "bindings": [
            {
                "source_story_id": STORY_ID,
                "event_key": EVENT_KEY,
                "chapter": "CH01",
            }
        ],
    }


@pytest.fixture
def condition_data():
    return {
        "case_id": "CASE-001",
        "conditions": [
            {
                "story_id": STORY_ID,
                "chapter": "CH01",
                "all_evidence": ["E01"],
                "any_evidence": [],
                "required_flags": ["TEST_EVENT_READY"],
            }
        ],
    }


def write_json(tmp_path, data, name="events.json"):
    path = tmp_path / name

    path.write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )

    return path


@pytest.fixture
def bindings(tmp_path, binding_data):
    return load_story_event_bindings(
        write_json(
            tmp_path,
            binding_data,
            "bindings.json",
        )
    )


def test_valid_bindings(bindings):
    binding = bindings[EVENT_KEY]

    assert binding.source_story_id == STORY_ID
    assert binding.event_key == EVENT_KEY
    assert binding.chapter == "CH01"


def test_bindings_are_readonly(bindings):
    with pytest.raises(TypeError):
        bindings[EVENT_KEY] = bindings[EVENT_KEY]


def test_empty_bindings_are_safe(tmp_path, binding_data):
    binding_data["bindings"] = []

    result = load_story_event_bindings(
        write_json(tmp_path, binding_data)
    )

    assert dict(result) == {}


def test_wrong_binding_case_is_rejected(
    tmp_path,
    binding_data,
):
    binding_data["case_id"] = "OTHER-CASE"

    with pytest.raises(ValueError):
        load_story_event_bindings(
            write_json(tmp_path, binding_data)
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_story_id", "INVALID"),
        ("source_story_id", "STORY_030"),
        ("event_key", "INVALID"),
        ("event_key", "EVT-CH02-001"),
        ("chapter", "CH99"),
    ],
)
def test_invalid_binding_is_rejected(
    tmp_path,
    binding_data,
    field,
    value,
):
    binding_data["bindings"][0][field] = value

    with pytest.raises(ValueError):
        load_story_event_bindings(
            write_json(tmp_path, binding_data)
        )


def test_duplicate_story_id_is_rejected(
    tmp_path,
    binding_data,
):
    binding_data["bindings"].append(
        {
            "source_story_id": STORY_ID,
            "event_key": "EVT-CH01-002",
            "chapter": "CH01",
        }
    )

    with pytest.raises(ValueError):
        load_story_event_bindings(
            write_json(tmp_path, binding_data)
        )


def test_duplicate_event_key_is_rejected(
    tmp_path,
    binding_data,
):
    binding_data["bindings"].append(
        {
            "source_story_id": "STORY_002",
            "event_key": EVENT_KEY,
            "chapter": "CH01",
        }
    )

    with pytest.raises(ValueError):
        load_story_event_bindings(
            write_json(tmp_path, binding_data)
        )


def test_extra_binding_field_is_rejected(
    tmp_path,
    binding_data,
):
    binding_data["bindings"][0]["approved"] = True

    with pytest.raises(ValueError):
        load_story_event_bindings(
            write_json(tmp_path, binding_data)
        )


def test_missing_binding_file_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_story_event_bindings(
            tmp_path / "missing.json"
        )


def test_invalid_json_is_rejected(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        load_story_event_bindings(path)


def test_valid_conditions(
    tmp_path,
    bindings,
    condition_data,
):
    result = load_story_event_conditions(
        write_json(tmp_path, condition_data),
        bindings=bindings,
    )

    rule = result[STORY_ID]

    assert rule.chapter == "CH01"
    assert rule.all_evidence == frozenset({"E01"})
    assert rule.any_evidence == frozenset()
    assert rule.required_flags == frozenset(
        {"TEST_EVENT_READY"}
    )


def test_conditions_are_readonly(
    tmp_path,
    bindings,
    condition_data,
):
    result = load_story_event_conditions(
        write_json(tmp_path, condition_data),
        bindings=bindings,
    )

    with pytest.raises(TypeError):
        result[STORY_ID] = result[STORY_ID]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("all_evidence", ["E31"]),
        ("all_evidence", "E01"),
        ("all_evidence", ["E01", "E01"]),
        ("any_evidence", [123]),
        ("required_flags", []),
        ("required_flags", ["invalid flag"]),
        ("chapter", "CH02"),
        ("story_id", "STORY_002"),
    ],
)
def test_invalid_conditions_are_rejected(
    tmp_path,
    bindings,
    condition_data,
    field,
    value,
):
    condition_data["conditions"][0][field] = value

    with pytest.raises(ValueError):
        load_story_event_conditions(
            write_json(tmp_path, condition_data),
            bindings=bindings,
        )


def test_missing_conditions_are_rejected(
    tmp_path,
    bindings,
    condition_data,
):
    condition_data["conditions"] = []

    with pytest.raises(ValueError):
        load_story_event_conditions(
            write_json(tmp_path, condition_data),
            bindings=bindings,
        )


def test_duplicate_conditions_are_rejected(
    tmp_path,
    bindings,
    condition_data,
):
    condition_data["conditions"].append(
        condition_data["conditions"][0].copy()
    )

    with pytest.raises(ValueError):
        load_story_event_conditions(
            write_json(tmp_path, condition_data),
            bindings=bindings,
        )


def test_extra_condition_field_is_rejected(
    tmp_path,
    bindings,
    condition_data,
):
    condition_data["conditions"][0]["enabled"] = True

    with pytest.raises(ValueError):
        load_story_event_conditions(
            write_json(tmp_path, condition_data),
            bindings=bindings,
        )


def test_empty_configuration_is_safe(tmp_path):
    result = load_story_event_conditions(
        write_json(
            tmp_path,
            {
                "case_id": "CASE-001",
                "conditions": [],
            },
        ),
        bindings={},
    )

    assert dict(result) == {}