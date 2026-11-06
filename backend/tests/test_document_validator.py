import json
from pathlib import Path

import pytest

from crimescene.scenario.loaders.document_loader import (
    load_player_documents,
)
from crimescene.scenario.loaders.evidence_loader import (
    load_evidence_rules,
)
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.validators.document_validator import (
    validate_document_evidence_references,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def make_document() -> PlayerDocument:
    """테스트용 플레이어 문서를 생성한다."""

    return PlayerDocument.model_validate(
        {
            "doc_id": "CASE001-DOC-E01",
            "case_id": "CASE-001",
            "title": "테스트 증거",
            "body": "테스트용 사건 기록입니다.",
            "family": "evidence",
            "access_scope": "collected_evidence",
            "truth_status": "documented_in_game",
            "source_evidence_ids": ["E01"],
            "known_by_character_ids": ["C01"],
            "source_doc_ids": ["CASE001-DOC-E01"],
            "required_evidence": [],
            "required_presentations": [],
            "required_flags": [],
            "required_ending": None,
            "protected_fact_ids": [],
            "incident_year": 2026,
            "incident_years": [2026],
            "source_refs": [
                {
                    "path": "evidence/CASE001-DOC-E01.md",
                    "sha256": "test-hash",
                    "json_pointer": "/",
                    "dereference_for_llm": False,
                }
            ],
            "record_id": "REC-TEST",
            "point_id": "POINT-TEST",
            "policy_id": "POL-TEST",
            "state_version": "1",
            "content_version": "1",
            "build_id": "TEST",
            "content_hash": "TEST",
            "search_text": "테스트 증거",
        }
    )


def make_evidence_rule() -> EvidenceRule:
    """테스트용 증거 규칙을 생성한다."""

    return EvidenceRule(
        name="테스트 증거",
        score=1,
        holder="C01",
        prerequisites=[],
        presentation=[],
        q=["이 증거에 대해 설명해 주세요."],
    )


@pytest.fixture
def sample_data():
    """참조 무결성 테스트용 기본 데이터."""

    documents = [make_document()]

    evidence_rules = {
        "E01": make_evidence_rule(),
    }

    return documents, evidence_rules


def validate(documents, evidence_rules):
    """테스트용 등록 정보를 사용하여 참조를 검사한다."""

    return validate_document_evidence_references(
        documents,
        evidence_rules,
        case_id="CASE-001",
        character_ids={"C01"},
        source_ids={"CASE001-DOC-E01"},
        flag_ids={"L01"},
    )


def test_valid_references(sample_data):
    """정상적인 참조는 오류가 없어야 한다."""

    documents, evidence_rules = sample_data

    assert validate(documents, evidence_rules) == []


@pytest.mark.parametrize(
    "field",
    [
        "source_evidence_ids",
        "required_evidence",
    ],
)
def test_unknown_evidence_reference(sample_data, field):
    """존재하지 않는 증거 ID를 탐지한다."""

    documents, evidence_rules = sample_data

    documents[0] = documents[0].model_copy(update={field: ["E99"]})

    violations = validate(documents, evidence_rules)

    assert any(field in item.path and "E99" in item.message for item in violations)


def test_unknown_character_reference(sample_data):
    """등록되지 않은 NPC ID를 탐지한다."""

    documents, evidence_rules = sample_data

    documents[0] = documents[0].model_copy(
        update={
            "known_by_character_ids": ["C99"],
        }
    )

    violations = validate(documents, evidence_rules)

    assert any(
        "known_by_character_ids" in item.path and "C99" in item.message
        for item in violations
    )


def test_unknown_source_document(sample_data):
    """등록되지 않은 출처 문서 ID를 탐지한다."""

    documents, evidence_rules = sample_data

    documents[0] = documents[0].model_copy(
        update={
            "source_doc_ids": ["DOC-UNKNOWN"],
        }
    )

    violations = validate(documents, evidence_rules)

    assert any(
        "source_doc_ids" in item.path and "DOC-UNKNOWN" in item.message
        for item in violations
    )


def test_unknown_flag_reference(sample_data):
    """존재하지 않는 게임 플래그를 탐지한다."""

    documents, evidence_rules = sample_data

    documents[0] = documents[0].model_copy(
        update={
            "required_flags": ["L99"],
        }
    )

    violations = validate(documents, evidence_rules)

    assert any(
        "required_flags" in item.path and "L99" in item.message for item in violations
    )


def test_invalid_presentation_format(sample_data):
    """NPC:증거 형식이 아닌 제시 조건을 차단한다."""

    documents, evidence_rules = sample_data

    documents[0] = documents[0].model_copy(
        update={
            "required_presentations": ["C01-E01"],
        }
    )

    violations = validate(documents, evidence_rules)

    assert any("잘못된 증거 제시 조건 형식" in item.message for item in violations)


@pytest.mark.parametrize(
    ("presentation", "expected_message"),
    [
        ("C99:E01", "존재하지 않는 NPC"),
        ("C01:E99", "존재하지 않는 증거"),
    ],
)
def test_invalid_presentation_reference(
    sample_data,
    presentation,
    expected_message,
):
    """증거 제시 조건의 NPC 또는 증거 참조 오류를 탐지한다."""

    documents, evidence_rules = sample_data

    documents[0] = documents[0].model_copy(
        update={
            "required_presentations": [presentation],
        }
    )

    violations = validate(documents, evidence_rules)

    assert any(expected_message in item.message for item in violations)


def test_document_case_id_mismatch(sample_data):
    """사건 ID가 다른 문서를 탐지한다."""

    documents, evidence_rules = sample_data

    documents[0] = documents[0].model_copy(update={"case_id": "CASE-999"})

    violations = validate(documents, evidence_rules)

    assert any(item.path == "documents[0].case_id" for item in violations)


def test_duplicate_document_id(sample_data):
    """중복 문서 ID를 탐지한다."""

    documents, evidence_rules = sample_data

    documents.append(documents[0].model_copy(deep=True))

    violations = validate(documents, evidence_rules)

    assert any("중복된 문서 ID" in item.message for item in violations)


def test_invalid_evidence_prerequisite(sample_data):
    """존재하지 않는 증거 선행 조건을 탐지한다."""

    documents, evidence_rules = sample_data

    evidence_rules["E01"] = make_evidence_rule().model_copy(
        update={
            "prerequisites": ["E99"],
        }
    )

    violations = validate(documents, evidence_rules)

    assert any(
        "prerequisites" in item.path and "E99" in item.message for item in violations
    )


@pytest.mark.parametrize(
    ("presentation", "expected_message"),
    [
        ("C99:E01", "존재하지 않는 NPC"),
        ("C01:E99", "존재하지 않는 증거"),
    ],
)
def test_invalid_evidence_rule_presentation(
    sample_data,
    presentation,
    expected_message,
):
    """증거 규칙에 포함된 잘못된 제시 조건을 탐지한다."""

    documents, evidence_rules = sample_data

    evidence_rules["E01"] = make_evidence_rule().model_copy(
        update={
            "presentation": [presentation],
        }
    )

    violations = validate(documents, evidence_rules)

    assert any(
        "evidence_rules[E01].presentation" in item.path
        and expected_message in item.message
        for item in violations
    )


def test_real_v71_document_evidence_references():
    """실제 v7.1 문서·증거 참조 무결성을 검증한다."""

    root = PROJECT_ROOT / ".local" / "case001_v7_1"

    matches = list(root.glob("*/data/player_documents.jsonl"))

    if not matches:
        pytest.skip("로컬 v7.1 데이터가 없습니다.")

    assert len(matches) == 1

    data_dir = matches[0].parent

    documents = load_player_documents(data_dir / "player_documents.jsonl")

    evidence_rules = load_evidence_rules(data_dir / "evidence_rules.json")

    def read_json(name):
        return json.loads((data_dir / name).read_text(encoding="utf-8-sig"))

    characters = read_json("character_registry.json")
    sources = read_json("source_registry.json")
    flags = read_json("flag_rules.json")

    npc_ids = {
        character_id for character_id in characters if character_id.startswith("C")
    }

    violations = validate_document_evidence_references(
        documents,
        evidence_rules,
        case_id="CASE-001",
        character_ids=npc_ids,
        source_ids=set(sources),
        flag_ids=set(flags),
    )

    assert len(documents) == 28
    assert len(evidence_rules) == 10
    assert len(npc_ids) == 10
    assert len(sources) == 163
    assert len(flags) == 5

    assert violations == []
