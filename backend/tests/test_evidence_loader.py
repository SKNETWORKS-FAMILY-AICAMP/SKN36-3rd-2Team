import json
from pathlib import Path

import pytest

from crimescene.scenario.loaders.evidence_loader import (
    load_evidence_rules,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def make_rule() -> dict:
    """테스트용 증거 규칙을 생성한다."""
    return {
        "name": "테스트 증거",
        "score": 1,
        "holder": "C01",
        "prerequisites": [],
        "presentation": [],
        "q": ["증거에 대해 설명해 주세요."],
    }


def write_rules(
    path: Path,
    rules: dict,
    *,
    encoding: str = "utf-8",
) -> None:
    """증거 규칙을 JSON 파일로 저장한다."""
    path.write_text(
        json.dumps(rules, ensure_ascii=False),
        encoding=encoding,
    )


def test_load_valid_evidence(tmp_path):
    """정상적인 증거 규칙을 읽는다."""
    path = tmp_path / "evidence.json"
    write_rules(path, {"E01": make_rule()})

    rules = load_evidence_rules(path)

    assert len(rules) == 1
    assert rules["E01"].name == "테스트 증거"
    assert rules["E01"].score == 1


def test_load_multiple_evidence(tmp_path):
    """여러 증거 규칙을 읽는다."""
    path = tmp_path / "evidence.json"

    write_rules(
        path,
        {
            "E01": make_rule(),
            "E02": make_rule(),
            "E03": make_rule(),
        },
    )

    rules = load_evidence_rules(path)

    assert len(rules) == 3
    assert set(rules) == {"E01", "E02", "E03"}


def test_utf8_bom_support(tmp_path):
    """UTF-8 BOM이 포함된 JSON 파일을 읽는다."""
    path = tmp_path / "evidence.json"

    write_rules(
        path,
        {"E01": make_rule()},
        encoding="utf-8-sig",
    )

    rules = load_evidence_rules(path)

    assert len(rules) == 1


def test_duplicate_evidence_key(tmp_path):
    """JSON에 증거 ID가 중복되면 차단한다."""
    path = tmp_path / "evidence.json"

    rule = json.dumps(make_rule(), ensure_ascii=False)

    path.write_text(
        f'{{"E01": {rule}, "E01": {rule}}}',
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="중복된 JSON Key: E01",
    ):
        load_evidence_rules(path)


def test_duplicate_nested_json_key(tmp_path):
    """증거 규칙 내부의 중복 필드도 차단한다."""
    path = tmp_path / "evidence.json"

    path.write_text(
        (
            '{"E01": {'
            '"name": "테스트", '
            '"score": 1, '
            '"score": 2, '
            '"holder": "C01", '
            '"prerequisites": [], '
            '"presentation": [], '
            '"q": []'
            "}}"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="중복된 JSON Key: score",
    ):
        load_evidence_rules(path)


def test_invalid_json(tmp_path):
    """잘못된 JSON 형식을 차단한다."""
    path = tmp_path / "evidence.json"

    path.write_text(
        '{"E01": invalid}',
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="증거 규칙 JSON 파싱 실패",
    ):
        load_evidence_rules(path)


def test_invalid_evidence_id(tmp_path):
    """E01 형식이 아닌 증거 ID를 차단한다."""
    path = tmp_path / "evidence.json"

    write_rules(path, {"E1": make_rule()})

    with pytest.raises(
        ValueError,
        match="증거 규칙 스키마 검증 실패",
    ):
        load_evidence_rules(path)


def test_missing_required_field(tmp_path):
    """필수 필드가 누락된 증거를 차단한다."""
    path = tmp_path / "evidence.json"

    rule = make_rule()
    del rule["name"]

    write_rules(path, {"E01": rule})

    with pytest.raises(
        ValueError,
        match="증거 규칙 스키마 검증 실패",
    ):
        load_evidence_rules(path)


def test_invalid_score_type(tmp_path):
    """문자열 점수를 정수로 자동 변환하지 않는다."""
    path = tmp_path / "evidence.json"

    rule = make_rule()
    rule["score"] = "3"

    write_rules(path, {"E01": rule})

    with pytest.raises(
        ValueError,
        match="증거 규칙 스키마 검증 실패",
    ):
        load_evidence_rules(path)


def test_negative_score(tmp_path):
    """음수 증거 점수를 차단한다."""
    path = tmp_path / "evidence.json"

    rule = make_rule()
    rule["score"] = -1

    write_rules(path, {"E01": rule})

    with pytest.raises(
        ValueError,
        match="증거 규칙 스키마 검증 실패",
    ):
        load_evidence_rules(path)


def test_empty_evidence_catalog(tmp_path):
    """증거 목록이 비어 있으면 오류를 발생시킨다."""
    path = tmp_path / "evidence.json"

    write_rules(path, {})

    with pytest.raises(
        ValueError,
        match="증거 규칙이 비어 있습니다",
    ):
        load_evidence_rules(path)


def test_real_v71_evidence_rules():
    """실제 v7.1 증거 규칙 E01~E10을 검증한다."""
    root = PROJECT_ROOT / ".local" / "case001_v7_1"

    matches = list(root.glob("*/data/evidence_rules.json"))

    if not matches:
        pytest.skip("로컬 v7.1 데이터가 없습니다.")

    assert len(matches) == 1

    rules = load_evidence_rules(matches[0])

    expected_ids = {f"E{i:02d}" for i in range(1, 11)}

    assert set(rules) == expected_ids
    assert len(rules) == 10

    total_score = sum(rule.score for rule in rules.values())

    total_questions = sum(len(rule.q) for rule in rules.values())

    assert total_score == 21
    assert total_questions == 50
