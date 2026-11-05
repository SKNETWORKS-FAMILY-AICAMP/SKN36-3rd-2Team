import json
from pathlib import Path

import pytest

from crimescene.scenario.loaders.character_loader import (
    load_character_profiles,
)
from crimescene.scenario.loaders.relationship_loader import (
    load_hidden_relationship_edges,
    load_relationship_edges,
)
from crimescene.scenario.schemas.character import CharacterProfile
from crimescene.scenario.schemas.relationship import (
    HiddenRelationshipEdge,
    RelationshipSourceEdge,
)
from crimescene.scenario.validators.relationship_validator import (
    validate_character_relationship_references,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def sample_data():
    """참조 무결성 검사에 필요한 테스트 데이터를 생성한다."""

    character = CharacterProfile.model_validate(
        {
            "id": "C01",
            "name": "윤태식",
            "voice": "차분한 말투",
            "appearance": "검은 정장",
            "initial": "사건에 대해 알고 있습니다.",
            "alibi": "당시 사무실에 있었습니다.",
            "secret_2026": "2026년 비밀",
            "secret_2016": "2016년 비밀",
            "trajectory": "점차 태도가 변화한다.",
            "questions": ["사건 당시 어디에 있었습니까?"],
            "cards": [
                {
                    "id": "K-C01-01",
                    "condition": "OPEN",
                    "topic": "사건",
                    "body": "사건에 대한 진술",
                    "stance": "character_claim",
                    "claim_group": "test",
                    "stage_priority": 0,
                    "supersedes": [],
                    "effects": {
                        "find": [],
                        "flags": [],
                    },
                }
            ],
        }
    )

    edge = RelationshipSourceEdge.model_validate(
        {
            "case_id": "CASE-001",
            "edge_id": "REL-001",
            "source_id": "C01",
            "target_id": "SCHOOL",
            "relation": "STAFF_AT",
            "incident_year": 2026,
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
            "temporal_precision": "day",
            "truth_status": "documented",
            "source_doc_ids": ["DOC-TEST"],
            "asserted_by": ["C02"],
            "access_scope": "public",
            "required_evidence": [],
            "required_presentations": [],
            "required_flags": [],
            "required_ending": None,
        }
    )

    hidden = HiddenRelationshipEdge.model_validate(
        {
            "source_id": "C01",
            "relation": "KNOWS",
            "target_id": "C02",
            "year": 2026,
            "access_scope": "admin_only",
        }
    )

    registry = [
        {
            "entity_id": "C01",
            "type": "Person",
            "label": "윤태식",
            "case_id": "CASE-001",
        },
        {
            "entity_id": "C02",
            "type": "Person",
            "label": "문지혜",
            "case_id": "CASE-001",
        },
        {
            "entity_id": "SCHOOL",
            "type": "Place",
            "label": "학교",
            "case_id": "CASE-001",
        },
    ]

    return {
        "characters": [character],
        "edges": [edge],
        "hidden": [hidden],
        "registry": registry,
    }


def validate(data):
    """테스트 데이터의 참조 무결성을 검사한다."""

    return validate_character_relationship_references(
        data["characters"],
        data["edges"],
        data["hidden"],
        data["registry"],
        case_id="CASE-001",
    )


def test_valid_relationship_references(sample_data):
    """정상적인 관계 데이터는 오류가 없어야 한다."""

    errors = validate(sample_data)

    assert errors == []


def test_unknown_character(sample_data):
    """등록되지 않은 NPC를 탐지한다."""

    sample_data["registry"] = [
        entity for entity in sample_data["registry"] if entity["entity_id"] != "C01"
    ]

    errors = validate(sample_data)

    assert any(error.path == "characters[0].id" for error in errors)


def test_character_name_mismatch(sample_data):
    """NPC 프로필과 등록된 이름이 다르면 탐지한다."""

    sample_data["registry"][0]["label"] = "다른 이름"

    errors = validate(sample_data)

    assert any(error.path == "characters[0].name" for error in errors)


@pytest.mark.parametrize(
    "field",
    ["source_id", "target_id"],
)
def test_unknown_relationship_entity(sample_data, field):
    """존재하지 않는 관계 엔티티를 탐지한다."""

    edge = sample_data["edges"][0]

    sample_data["edges"] = [edge.model_copy(update={field: "UNKNOWN"})]

    errors = validate(sample_data)

    assert any(error.path == f"edges[0].{field}" for error in errors)


def test_unknown_asserted_by(sample_data):
    """등록되지 않은 진술자를 탐지한다."""

    edge = sample_data["edges"][0]

    sample_data["edges"] = [edge.model_copy(update={"asserted_by": ["UNKNOWN"]})]

    errors = validate(sample_data)

    assert any(error.path == "edges[0].asserted_by[0]" for error in errors)


def test_unknown_hidden_entity(sample_data):
    """비밀 관계에서 존재하지 않는 엔티티를 탐지한다."""

    hidden = sample_data["hidden"][0]

    sample_data["hidden"] = [hidden.model_copy(update={"target_id": "UNKNOWN"})]

    errors = validate(sample_data)

    assert any(error.path == "hidden_edges[0].target_id" for error in errors)


def test_relationship_case_mismatch(sample_data):
    """관계의 사건 ID 불일치를 탐지한다."""

    edge = sample_data["edges"][0]

    sample_data["edges"] = [edge.model_copy(update={"case_id": "CASE-999"})]

    errors = validate(sample_data)

    assert any(error.path == "edges[0].case_id" for error in errors)


def test_duplicate_entity_id(sample_data):
    """중복된 엔티티 ID를 탐지한다."""

    sample_data["registry"].append(sample_data["registry"][0].copy())

    errors = validate(sample_data)

    assert any("중복된 엔티티 ID" in error.message for error in errors)


def test_entity_case_mismatch(sample_data):
    """엔티티 등록 정보의 사건 ID 불일치를 탐지한다."""

    sample_data["registry"][2]["case_id"] = "CASE-999"

    errors = validate(sample_data)

    assert any(error.path == "entity_registry[2].case_id" for error in errors)


def test_invalid_npc_entity_type(sample_data):
    """NPC가 Person 유형으로 등록됐는지 검사한다."""

    sample_data["registry"][0]["type"] = "Place"

    errors = validate(sample_data)

    assert any(error.path == "characters[0].id" for error in errors)


def test_real_v71_relationship_integrity():
    """실제 v7.1 데이터의 참조 무결성을 확인한다."""

    root = PROJECT_ROOT / ".local" / "case001_v7_1"

    if not root.is_dir():
        pytest.skip("로컬 v7.1 데이터가 없습니다.")

    def find_file(pattern):
        matches = list(root.glob(pattern))
        assert len(matches) == 1, matches
        return matches[0]

    characters = load_character_profiles(find_file("*/data/characters.json"))

    edges = load_relationship_edges(find_file("*/admin/relationship_edges_source.json"))

    hidden = load_hidden_relationship_edges(
        find_file("*/admin/hidden_relationship_edges.json")
    )

    registry = json.loads(
        find_file("*/data/entity_registry.json").read_text(encoding="utf-8-sig")
    )

    errors = validate_character_relationship_references(
        characters,
        edges,
        hidden,
        registry,
        case_id="CASE-001",
    )

    assert len(characters) == 10
    assert len(registry) == 30
    assert len(edges) == 37
    assert len(hidden) == 4

    assert not errors, [f"{error.path}: {error.message}" for error in errors]
