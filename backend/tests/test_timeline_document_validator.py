import json
from pathlib import Path

import pytest

from crimescene.scenario.loaders.document_loader import (
    load_player_documents,
)
from crimescene.scenario.schemas.document import PlayerDocument
from crimescene.scenario.validators.timeline_document_validator import (
    validate_timeline_document_metadata,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def sample_data():
    """테스트용 문서와 관리자 타임라인."""

    document = PlayerDocument(
        doc_id="CASE001-DOC-TEST",
        case_id="CASE-001",
        title="테스트 문서",
        body="테스트용 사건 기록",
        family="evidence",
        access_scope="collected_evidence",
        truth_status="documented_in_game",
        source_evidence_ids=["E01"],
        known_by_character_ids=[],
        source_doc_ids=["CASE001-DOC-TEST"],
        required_evidence=[],
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        protected_fact_ids=[],
        incident_year=2026,
        incident_years=[2026],
        source_refs=[
            {
                "path": "evidence/test.md",
                "sha256": "test",
                "json_pointer": "/",
                "dereference_for_llm": True,
            }
        ],
        record_id="REC-TEST",
        point_id="POINT-TEST",
        policy_id="POL-TEST",
        state_version="1",
        content_version="1",
        build_id="TEST",
        content_hash="TEST",
        search_text="테스트 문서",
    )

    timeline = [
        {
            "event_id": "EV-001",
            "case_id": "CASE-001",
            "incident_year": 2026,
            "access_scope": "admin_only",
            "source_refs": [{"path": "admin/test.md"}],
        }
    ]

    return [document], timeline


def validate(documents, timeline):
    return validate_timeline_document_metadata(
        documents,
        timeline,
        case_id="CASE-001",
    )


def test_valid_metadata(sample_data):
    """정상적인 데이터는 오류가 없어야 한다."""

    documents, timeline = sample_data

    assert validate(documents, timeline) == []


def test_document_year_not_in_timeline_is_allowed(sample_data):
    """문서가 언급한 모든 연도가 타임라인에 있을 필요는 없다."""

    documents, timeline = sample_data

    documents[0] = documents[0].model_copy(
        update={
            "incident_years": [2025, 2026],
        }
    )

    assert validate(documents, timeline) == []


def test_duplicate_event_id(sample_data):
    """중복된 이벤트 ID를 탐지한다."""

    documents, timeline = sample_data

    timeline.append(timeline[0].copy())

    violations = validate(documents, timeline)

    assert any("중복된 이벤트 ID" in item.message for item in violations)


def test_missing_event_id(sample_data):
    """이벤트 ID가 없는 경우 오류를 반환한다."""

    documents, timeline = sample_data

    timeline[0]["event_id"] = ""

    violations = validate(documents, timeline)

    assert any("이벤트 ID가 없습니다" in item.message for item in violations)


def test_timeline_case_id_mismatch(sample_data):
    """잘못된 사건 ID를 탐지한다."""

    documents, timeline = sample_data

    timeline[0]["case_id"] = "CASE-999"

    violations = validate(documents, timeline)

    assert any(item.path == "timeline[0].case_id" for item in violations)


def test_timeline_access_scope(sample_data):
    """관리자 타임라인은 공개되면 안 된다."""

    documents, timeline = sample_data

    timeline[0]["access_scope"] = "public"

    violations = validate(documents, timeline)

    assert any(item.path == "timeline[0].access_scope" for item in violations)


@pytest.mark.parametrize(
    "invalid_year",
    ["2026", True, None],
)
def test_invalid_timeline_year(sample_data, invalid_year):
    """잘못된 사건 연도 타입을 탐지한다."""

    documents, timeline = sample_data

    timeline[0]["incident_year"] = invalid_year

    violations = validate(documents, timeline)

    assert any(item.path == "timeline[0].incident_year" for item in violations)


@pytest.mark.parametrize(
    "target",
    ["timeline", "document"],
)
def test_missing_source_refs(sample_data, target):
    """출처가 없는 데이터를 탐지한다."""

    documents, timeline = sample_data

    if target == "timeline":
        timeline[0]["source_refs"] = []
    else:
        documents[0] = documents[0].model_copy(update={"source_refs": []})

    violations = validate(documents, timeline)

    assert any("source_refs" in item.path for item in violations)


@pytest.mark.parametrize(
    "target",
    ["timeline", "document"],
)
def test_invalid_source_path(sample_data, target):
    """출처 파일 경로가 비어 있으면 오류를 반환한다."""

    documents, timeline = sample_data

    if target == "timeline":
        timeline[0]["source_refs"] = [{"path": ""}]
    else:
        documents[0] = documents[0].model_copy(update={"source_refs": [{"path": ""}]})

    violations = validate(documents, timeline)

    assert any(item.path.endswith(".path") for item in violations)


def test_document_case_id_mismatch(sample_data):
    """문서 사건 ID 불일치를 탐지한다."""

    documents, timeline = sample_data

    documents[0] = documents[0].model_copy(update={"case_id": "CASE-999"})

    violations = validate(documents, timeline)

    assert any(item.path == "documents[0].case_id" for item in violations)


def test_document_year_mismatch(sample_data):
    """문서의 발생 연도와 연도 목록 불일치를 탐지한다."""

    documents, timeline = sample_data

    documents[0] = documents[0].model_copy(
        update={
            "incident_year": 2026,
            "incident_years": [2016],
        }
    )

    violations = validate(documents, timeline)

    assert any(item.path == "documents[0].incident_year" for item in violations)


def test_nullable_document_year(sample_data):
    """발생 연도가 NULL인 문서를 허용한다."""

    documents, timeline = sample_data

    documents[0] = documents[0].model_copy(
        update={
            "incident_year": None,
            "incident_years": [2016, 2026],
        }
    )

    assert validate(documents, timeline) == []


def test_real_v71_timeline_documents():
    """실제 v7.1 관리자 타임라인과 문서를 검증한다."""

    source_root = PROJECT_ROOT / ".local" / "case001_v7_1"

    matches = list(source_root.glob("*/data/timeline_events.json"))

    if not matches:
        pytest.skip("로컬 v7.1 데이터가 없습니다.")

    assert len(matches) == 1

    data_dir = matches[0].parent

    timeline = json.loads(
        (data_dir / "timeline_events.json").read_text(encoding="utf-8-sig")
    )

    documents = load_player_documents(data_dir / "player_documents.jsonl")

    violations = validate(
        documents,
        timeline,
    )

    assert len(timeline) == 95
    assert len(documents) == 28
    assert violations == []
