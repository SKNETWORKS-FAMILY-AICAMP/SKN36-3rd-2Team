import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from crimescene.scenario.loaders.character_loader import (
    load_character_profiles,
)
from crimescene.scenario.loaders.statement_assessment_loader import (
    load_statement_assessments,
)
from crimescene.scenario.schemas.character import CharacterProfile
from crimescene.scenario.statement_assessment import (
    StatementIntent,
    StatementTruthStatus,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def make_character() -> CharacterProfile:
    """테스트용 NPC 프로필을 생성한다."""

    return CharacterProfile.model_validate(
        {
            "id": "C01",
            "name": "테스트 인물",
            "voice": "차분한 말투",
            "appearance": "검은 정장",
            "initial": "사건을 잘 모릅니다.",
            "alibi": "당시 사무실에 있었습니다.",
            "secret_2026": "2026년 비밀",
            "secret_2016": "2016년 비밀",
            "trajectory": "진술이 점차 변화한다.",
            "questions": ["사건 당시 어디에 있었나요?"],
            "cards": [
                {
                    "id": "K-C01-01",
                    "condition": "OPEN",
                    "topic": "알리바이",
                    "body": "저는 사무실에 있었습니다.",
                    "stance": "character_claim",
                    "claim_group": "alibi",
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


def make_override(**changes) -> dict:
    """테스트용 관리자 진술 평가를 생성한다."""

    data = {
        "assessment_id": "AST-K-C01-01",
        "case_id": "CASE-001",
        "npc_id": "C01",
        "knowledge_id": "K-C01-01",
        "truth_status": "FALSE",
        "statement_intent": "DECEPTIVE",
        "related_event_ids": [],
        "explanation": "테스트용 관리자 판정입니다.",
        "source_refs": [
            {
                "document_id": "admin/test.md",
                "section": "1",
            }
        ],
        "access_scope": "ENGINE_ONLY",
    }

    data.update(changes)

    return data


def load_test_data(tmp_path, overrides):
    """임시 JSON 파일을 이용해 진술 평가를 로딩한다."""

    path = tmp_path / "overrides.json"

    path.write_text(
        json.dumps(overrides, ensure_ascii=False),
        encoding="utf-8",
    )

    return load_statement_assessments(
        [make_character()],
        path,
        case_id="CASE-001",
    )


def test_valid_override(tmp_path):
    """정상적인 관리자 판정이 적용된다."""

    assessments = load_test_data(
        tmp_path,
        [make_override()],
    )

    assert len(assessments) == 1

    assessment = assessments[0]

    assert assessment.truth_status == StatementTruthStatus.FALSE
    assert assessment.statement_intent == StatementIntent.DECEPTIVE
    assert assessment.access_scope == "ENGINE_ONLY"


def test_no_overrides(tmp_path):
    """관리자 판정이 없으면 초기값을 유지한다."""

    assessments = load_test_data(tmp_path, [])

    assert len(assessments) == 1

    assert assessments[0].truth_status == StatementTruthStatus.UNVERIFIED

    assert assessments[0].statement_intent == StatementIntent.UNKNOWN


def test_duplicate_override_id(tmp_path):
    """중복된 진술 평가 ID를 차단한다."""

    override = make_override()

    with pytest.raises(ValueError, match="중복된 진술 평가 ID"):
        load_test_data(
            tmp_path,
            [override, override.copy()],
        )


def test_unknown_assessment_id(tmp_path):
    """존재하지 않는 평가 ID를 차단한다."""

    override = make_override(
        assessment_id="AST-UNKNOWN",
    )

    with pytest.raises(ValueError, match="존재하지 않는 진술 평가"):
        load_test_data(tmp_path, [override])


@pytest.mark.parametrize(
    ("field", "invalid_value", "message"),
    [
        ("case_id", "CASE-999", "사건 ID"),
        ("npc_id", "C02", "NPC ID"),
        ("knowledge_id", "K-C02-01", "지식 카드 ID"),
    ],
)
def test_mismatched_reference(
    tmp_path,
    field,
    invalid_value,
    message,
):
    """사건·NPC·지식 카드 참조 불일치를 차단한다."""

    override = make_override(**{field: invalid_value})

    with pytest.raises(ValueError, match=message):
        load_test_data(tmp_path, [override])


@pytest.mark.parametrize(
    ("field", "invalid_value", "message"),
    [
        ("source_refs", [], "출처"),
        ("explanation", "", "설명"),
    ],
)
def test_classified_override_requires_basis(
    tmp_path,
    field,
    invalid_value,
    message,
):
    """확정된 판정에는 출처와 설명이 모두 필요하다."""

    override = make_override(**{field: invalid_value})

    with pytest.raises(ValueError, match=message):
        load_test_data(tmp_path, [override])


def test_invalid_truth_status(tmp_path):
    """정의되지 않은 진실 상태를 차단한다."""

    override = make_override(
        truth_status="INVALID",
    )

    with pytest.raises(ValidationError):
        load_test_data(tmp_path, [override])


def test_real_v71_statement_assessments():
    """실제 v7.1 NPC 진술 평가 26개를 검증한다."""

    source_root = PROJECT_ROOT / ".local" / "case001_v7_1"

    override_path = (
        PROJECT_ROOT
        / "backend"
        / "data"
        / "scenario"
        / "engine_only"
        / "statement_assessment_overrides.json"
    )

    matches = list(source_root.glob("*/data/characters.json"))

    if not matches or not override_path.is_file():
        pytest.skip("로컬 v7.1 관리자 데이터가 없습니다.")

    assert len(matches) == 1

    characters = load_character_profiles(matches[0])

    assessments = load_statement_assessments(
        characters,
        override_path,
        case_id="CASE-001",
    )

    assert len(characters) == 10
    assert len(assessments) == 26

    classified = [
        assessment
        for assessment in assessments
        if assessment.truth_status != StatementTruthStatus.UNVERIFIED
    ]

    deceptive = [
        assessment
        for assessment in assessments
        if assessment.statement_intent == StatementIntent.DECEPTIVE
    ]

    assert len(classified) == 1
    assert len(deceptive) == 1

    assert all(assessment.access_scope == "ENGINE_ONLY" for assessment in assessments)
