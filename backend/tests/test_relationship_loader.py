import json
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from crimescene.scenario.loaders.relationship_loader import (
    load_hidden_relationship_edges,
    load_relationship_edges,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def make_relationship(
    edge_id="REL-001",
    **overrides,
):
    """테스트용 일반 관계 데이터를 생성한다."""

    data = {
        "case_id": "CASE-001",
        "edge_id": edge_id,
        "source_id": "C01",
        "target_id": "C02",
        "relation": "KNOWS",
        "incident_year": 2026,
        "valid_from": "2026-01-01",
        "valid_to": "2026-12-31",
        "temporal_precision": "day",
        "truth_status": "documented",
        "source_doc_ids": ["DOC-TEST-001"],
        "asserted_by": [],
        "access_scope": "public",
        "required_evidence": [],
        "required_presentations": [],
        "required_flags": [],
        "required_ending": None,
    }

    data.update(overrides)

    return data


def make_hidden_relationship(**overrides):
    """테스트용 관리자 비밀 관계 데이터를 생성한다."""

    data = {
        "source_id": "C01",
        "relation": "KNOWS",
        "target_id": "C02",
        "year": 2026,
        "access_scope": "admin_only",
    }

    data.update(overrides)

    return data


def write_json(tmp_path, filename, data):
    """테스트 데이터를 임시 JSON 파일에 저장한다."""

    path = tmp_path / filename

    path.write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )

    return path


def test_load_valid_relationship(tmp_path):
    """정상 관계 데이터 로딩."""

    path = write_json(
        tmp_path,
        "relationships.json",
        [make_relationship()],
    )

    edges = load_relationship_edges(path)

    assert len(edges) == 1
    assert edges[0].edge_id == "REL-001"
    assert edges[0].source_id == "C01"
    assert edges[0].target_id == "C02"


def test_duplicate_relationship_id(tmp_path):
    """동일한 관계 ID 중복을 차단한다."""

    data = [
        make_relationship("REL-001"),
        make_relationship(
            "REL-001",
            source_id="C03",
            target_id="C04",
        ),
    ]

    path = write_json(
        tmp_path,
        "relationships.json",
        data,
    )

    with pytest.raises(ValueError, match="중복된 관계 ID"):
        load_relationship_edges(path)


def test_missing_required_relationship_field(tmp_path):
    """필수 관계 정보 누락을 차단한다."""

    relationship = make_relationship()

    del relationship["source_id"]

    path = write_json(
        tmp_path,
        "relationships.json",
        [relationship],
    )

    with pytest.raises(ValidationError):
        load_relationship_edges(path)


def test_invalid_relationship_access_scope(tmp_path):
    """관리자 전용 관계가 일반 관계에 섞이는 것을 차단한다."""

    relationship = make_relationship(
        access_scope="admin_only",
    )

    path = write_json(
        tmp_path,
        "relationships.json",
        [relationship],
    )

    with pytest.raises(ValidationError):
        load_relationship_edges(path)


def test_invalid_relationship_date_range(tmp_path):
    """관계 종료일이 시작일보다 빠르면 차단한다."""

    relationship = make_relationship(
        valid_from="2026-12-31",
        valid_to="2026-01-01",
    )

    path = write_json(
        tmp_path,
        "relationships.json",
        [relationship],
    )

    with pytest.raises(ValidationError):
        load_relationship_edges(path)


def test_empty_relationship_list(tmp_path):
    """비어 있는 일반 관계 목록을 차단한다."""

    path = write_json(
        tmp_path,
        "relationships.json",
        [],
    )

    with pytest.raises(ValueError, match="비어 있습니다"):
        load_relationship_edges(path)


def test_load_valid_hidden_relationship(tmp_path):
    """정상 관리자 비밀 관계 로딩."""

    path = write_json(
        tmp_path,
        "hidden.json",
        [make_hidden_relationship()],
    )

    edges = load_hidden_relationship_edges(path)

    assert len(edges) == 1
    assert edges[0].source_id == "C01"
    assert edges[0].access_scope == "admin_only"


def test_duplicate_hidden_relationship(tmp_path):
    """동일한 관리자 비밀 관계 중복을 차단한다."""

    relationship = make_hidden_relationship()

    path = write_json(
        tmp_path,
        "hidden.json",
        [relationship, relationship.copy()],
    )

    with pytest.raises(
        ValueError,
        match="중복된 관리자 비밀 관계",
    ):
        load_hidden_relationship_edges(path)


def test_invalid_hidden_access_scope(tmp_path):
    """관리자 비밀 관계의 공개 설정을 차단한다."""

    relationship = make_hidden_relationship(
        access_scope="public",
    )

    path = write_json(
        tmp_path,
        "hidden.json",
        [relationship],
    )

    with pytest.raises(ValidationError):
        load_hidden_relationship_edges(path)


def test_empty_hidden_relationship_list(tmp_path):
    """비어 있는 비밀 관계 목록을 차단한다."""

    path = write_json(
        tmp_path,
        "hidden.json",
        [],
    )

    with pytest.raises(ValueError, match="비어 있습니다"):
        load_hidden_relationship_edges(path)


def test_real_v71_relationships():
    """실제 v7.1 관계 37개와 비밀 관계 4개를 검증한다."""

    root = PROJECT_ROOT / ".local" / "case001_v7_1"

    edge_files = list(root.glob("*/admin/relationship_edges_source.json"))

    hidden_files = list(root.glob("*/admin/hidden_relationship_edges.json"))

    if not edge_files and not hidden_files:
        pytest.skip("로컬 v7.1 원본 데이터가 없습니다.")

    assert len(edge_files) == 1
    assert len(hidden_files) == 1

    edges = load_relationship_edges(edge_files[0])

    hidden = load_hidden_relationship_edges(hidden_files[0])

    # 전체 데이터 개수
    assert len(edges) == 37
    assert len(hidden) == 4

    # 관계 ID 중복 검사
    edge_ids = [edge.edge_id for edge in edges]

    assert len(edge_ids) == len(set(edge_ids))

    # 접근 범위별 개수
    access_scopes = Counter(edge.access_scope for edge in edges)

    assert access_scopes["public"] == 4
    assert access_scopes["conditional"] == 32
    assert access_scopes["ending_only"] == 1

    # 관계 진실 상태별 개수
    truth_statuses = Counter(edge.truth_status for edge in edges)

    assert truth_statuses["documented"] == 17
    assert truth_statuses["witness_statement"] == 16
    assert truth_statuses["hypothesis"] == 3
    assert truth_statuses["uncorroborated_claim"] == 1

    # 관리자 비밀 관계 검증
    assert all(edge.access_scope == "admin_only" for edge in hidden)
