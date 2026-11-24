"""Issue #146 - 서버 전용 챕터 규칙 로더 검증."""

import json

import pytest

from crimescene.scenario.loaders.chapter_rules_loader import (
    load_chapter_rules,
)


@pytest.fixture
def rules_data():
    return {
        "case_id": "CASE-001",
        "chapters": {
            f"CH0{i}": {
                "required_evidence": ["E01"],
                "required_flags": ["TEST_READY"],
                "required_presentations": ["C01:E01"],
            }
            for i in range(1, 5)
        },
    }


def write_rules(tmp_path, data):
    path = tmp_path / "chapter_rules.json"

    path.write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )

    return path


def test_load_valid_chapter_rules(tmp_path, rules_data):
    rules = load_chapter_rules(
        write_rules(tmp_path, rules_data)
    )

    assert set(rules) == {
        "CH01",
        "CH02",
        "CH03",
        "CH04",
    }

    assert rules["CH01"].target_chapter == "CH01"
    assert rules["CH01"].required_evidence == frozenset(
        {"E01"}
    )
    assert rules["CH01"].required_flags == frozenset(
        {"TEST_READY"}
    )
    assert rules["CH01"].required_presentations == frozenset(
        {"C01:E01"}
    )


def test_loaded_rules_are_readonly(tmp_path, rules_data):
    rules = load_chapter_rules(
        write_rules(tmp_path, rules_data)
    )

    with pytest.raises(TypeError):
        rules["CH01"] = rules["CH02"]


def test_wrong_case_is_rejected(tmp_path, rules_data):
    rules_data["case_id"] = "CASE-999"

    with pytest.raises(ValueError):
        load_chapter_rules(
            write_rules(tmp_path, rules_data)
        )


def test_missing_chapter_is_rejected(tmp_path, rules_data):
    rules_data["chapters"].pop("CH04")

    with pytest.raises(ValueError):
        load_chapter_rules(
            write_rules(tmp_path, rules_data)
        )


def test_unknown_chapter_is_rejected(tmp_path, rules_data):
    rules_data["chapters"]["CH05"] = (
        rules_data["chapters"]["CH04"].copy()
    )

    with pytest.raises(ValueError):
        load_chapter_rules(
            write_rules(tmp_path, rules_data)
        )


def test_missing_condition_field_is_rejected(
    tmp_path,
    rules_data,
):
    rules_data["chapters"]["CH01"].pop(
        "required_flags"
    )

    with pytest.raises(ValueError):
        load_chapter_rules(
            write_rules(tmp_path, rules_data)
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("required_evidence", "E01"),
        ("required_evidence", [1]),
        ("required_evidence", ["E01", "E01"]),
        ("required_evidence", ["E31"]),
        ("required_flags", [""]),
        ("required_presentations", ["C99:E01"]),
        ("required_presentations", ["E01"]),
    ],
)
def test_invalid_conditions_are_rejected(
    tmp_path,
    rules_data,
    field,
    value,
):
    rules_data["chapters"]["CH01"][field] = value

    with pytest.raises(ValueError):
        load_chapter_rules(
            write_rules(tmp_path, rules_data)
        )


def test_empty_rule_is_rejected(tmp_path, rules_data):
    rules_data["chapters"]["CH01"] = {
        "required_evidence": [],
        "required_flags": [],
        "required_presentations": [],
    }

    with pytest.raises(ValueError):
        load_chapter_rules(
            write_rules(tmp_path, rules_data)
        )


def test_invalid_json_is_rejected(tmp_path):
    path = tmp_path / "invalid.json"

    path.write_text(
        "{invalid json}",
        encoding="utf-8",
    )

    with pytest.raises(json.JSONDecodeError):
        load_chapter_rules(path)


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_chapter_rules(
            tmp_path / "missing.json"
        )