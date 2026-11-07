"""CASE-001 데이터 적재 무결성 테스트."""

from uuid import NAMESPACE_URL, uuid5

import pytest

from crimescene.db.ingest_integrity import (
    validate_neo4j_records,
    validate_qdrant_records,
)
from crimescene.ingest.chunk_models import RAGChunk
from crimescene.ingest.hybrid_chunker import HybridChunkRecord
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.relationship import RelationshipSourceEdge
from crimescene.scenario.source_timeline import SourceTimelineEvent


def make_record(
    source_id="DOC-001",
    *,
    source_type="player_document",
    index=0,
    count=1,
):
    """테스트용 Hybrid 청크 생성."""

    parent_id = uuid5(
        NAMESPACE_URL,
        f"CASE-001:{source_type}:{source_id}",
    )

    point_id = parent_id if index == 0 else uuid5(parent_id, f"rag-chunk:{index}")

    chunk = RAGChunk(
        chunk_id=point_id,
        source_id=source_id,
        source_type=source_type,
        case_id="CASE-001",
        policy_id="POL-TEST-001",
        family="evidence",
        access_scope=(
            "character_only" if source_type == "npc_knowledge" else "collected_evidence"
        ),
        character_id=("C01" if source_type == "npc_knowledge" else None),
        incident_year=2026,
        content_hash=f"hash-{source_id}",
        search_text=f"테스트 문서 {index}",
        body=f"테스트 문서 {index}",
    )

    return HybridChunkRecord(
        chunk=chunk,
        parent_point_id=parent_id,
        chunk_index=index,
        chunk_count=count,
    )


def validate_vector(records):
    """공통 테스트용 Qdrant 검증 실행."""

    return validate_qdrant_records(
        records,
        document_ids={"DOC-001", "DOC-002"},
        npc_card_ids={"CARD-001"},
        valid_policy_ids={"POL-TEST-001"},
    )


@pytest.fixture
def graph_data():
    """Neo4j 검증용 최소 사건 데이터."""

    entities = [
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
            "entity_id": "E01",
            "type": "Evidence",
            "label": "E01",
            "case_id": "CASE-001",
        },
    ]

    relationship = RelationshipSourceEdge.model_validate(
        {
            "case_id": "CASE-001",
            "edge_id": "REL-001",
            "source_id": "C01",
            "target_id": "C02",
            "relation": "KNOWS",
            "incident_year": 2026,
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
            "temporal_precision": "day",
            "truth_status": "documented",
            "source_doc_ids": [],
            "asserted_by": [],
            "access_scope": "conditional",
            "required_evidence": ["E01"],
            "required_presentations": [],
            "required_flags": [],
            "required_ending": None,
        }
    )

    rules = {
        "E01": EvidenceRule(
            name="테스트 증거",
            score=1,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
    }

    event = SourceTimelineEvent.model_validate(
        {
            "event_id": "EVT-TEST-001",
            "case_id": "CASE-001",
            "incident_year": 2026,
            "year_start": 2026,
            "year_end": 2026,
            "temporal_precision": "day",
            "raw_time": "2026-01-01",
            "event": "테스트 사건",
            "named_entity_ids": ["C01"],
            "source_note": "테스트",
            "source_refs": [{"path": "test.md"}],
            "truth_status": "admin_canonical",
            "access_scope": "admin_only",
        }
    )

    return {
        "entities": entities,
        "relationships": [relationship],
        "evidence_rules": rules,
        "events": [event],
    }


# ============================================================
# Qdrant 무결성 검사
# ============================================================


def test_qdrant_valid_records():
    """정상 청크와 NPC 카드 참조를 검증한다."""

    records = [
        make_record(index=0, count=2),
        make_record(index=1, count=2),
        make_record(
            "CARD-001",
            source_type="npc_knowledge",
        ),
    ]

    result = validate_vector(records)

    assert result.point_count == 3
    assert result.source_count == 2


def test_qdrant_duplicate_uuid():
    """동일 Point UUID 중복을 차단한다."""

    record = make_record()

    with pytest.raises(ValueError, match="중복 Qdrant"):
        validate_vector([record, record])


def test_qdrant_unknown_document():
    """등록되지 않은 문서 ID를 차단한다."""

    with pytest.raises(ValueError, match="등록되지 않은 문서"):
        validate_vector([make_record("DOC-999")])


def test_qdrant_unknown_npc_card():
    """등록되지 않은 NPC 카드 ID를 차단한다."""

    with pytest.raises(ValueError, match="등록되지 않은 NPC"):
        validate_vector(
            [
                make_record(
                    "CARD-999",
                    source_type="npc_knowledge",
                )
            ]
        )


def test_qdrant_missing_chunk():
    """청크가 누락된 원본을 차단한다."""

    with pytest.raises(ValueError, match="청크 누락"):
        validate_vector([make_record(index=0, count=2)])


def test_qdrant_unknown_policy():
    """등록되지 않은 접근 정책을 차단한다."""

    record = make_record()

    invalid_chunk = record.chunk.model_copy(update={"policy_id": "POL-UNKNOWN"})

    invalid_record = HybridChunkRecord(
        chunk=invalid_chunk,
        parent_point_id=record.parent_point_id,
        chunk_index=record.chunk_index,
        chunk_count=record.chunk_count,
    )

    with pytest.raises(ValueError, match="접근 정책"):
        validate_vector([invalid_record])


# ============================================================
# Neo4j 무결성 검사
# ============================================================


def test_neo4j_valid_graph(graph_data):
    """정상적인 관계·증거·사건 데이터를 검증한다."""

    result = validate_neo4j_records(**graph_data)

    assert result.entity_count == 3
    assert result.relationship_count == 1
    assert result.evidence_count == 1
    assert result.event_count == 1
    assert result.mention_count == 1


def test_neo4j_unknown_evidence_holder(graph_data):
    """증거 보유자가 존재하지 않으면 차단한다."""

    graph_data["evidence_rules"]["E01"] = graph_data["evidence_rules"][
        "E01"
    ].model_copy(update={"holder": "C99"})

    with pytest.raises(ValueError, match="증거 보유자"):
        validate_neo4j_records(**graph_data)


def test_neo4j_unknown_required_evidence(graph_data):
    """관계에서 참조하는 증거가 없으면 차단한다."""

    graph_data["relationships"] = [
        graph_data["relationships"][0].model_copy(update={"required_evidence": ["E99"]})
    ]

    with pytest.raises(ValueError, match="관계 증거"):
        validate_neo4j_records(**graph_data)


def test_neo4j_unknown_event_entity(graph_data):
    """사건의 인물 참조가 존재하지 않으면 차단한다."""

    graph_data["events"] = [
        graph_data["events"][0].model_copy(update={"named_entity_ids": ["C99"]})
    ]

    with pytest.raises(ValueError, match="등록되지 않은"):
        validate_neo4j_records(**graph_data)


def test_neo4j_duplicate_event(graph_data):
    """중복된 사건 ID를 차단한다."""

    event = graph_data["events"][0]

    graph_data["events"] = [event, event]

    with pytest.raises(ValueError, match="중복 사건"):
        validate_neo4j_records(**graph_data)
