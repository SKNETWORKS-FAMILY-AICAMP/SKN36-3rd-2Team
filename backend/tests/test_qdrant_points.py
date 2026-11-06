"""RAG 청크 → Qdrant Point 변환 단위 테스트."""

from dataclasses import replace
from uuid import UUID

import pytest

from crimescene.db.qdrant_collection import (
    DENSE_VECTOR_NAME,
    DENSE_VECTOR_SIZE,
)
from crimescene.db.qdrant_points import build_qdrant_point
from crimescene.ingest.chunk_models import RAGChunk
from crimescene.ingest.hybrid_chunker import HybridChunkRecord

POINT_ID = UUID("550e8400-e29b-41d4-a716-446655440000")


@pytest.fixture
def record():
    """가상의 플레이어 증거 청크."""

    chunk = RAGChunk(
        chunk_id=POINT_ID,
        source_id="DOC-TEST-001",
        source_type="player_document",
        case_id="CASE-001",
        policy_id="POL-TEST-001",
        family="evidence",
        access_scope="collected_evidence",
        character_id=None,
        incident_year=2016,
        content_hash="test-content-hash",
        search_text="사건 당일의 출입 기록",
        body="사건 당일의 출입 기록",
    )

    return HybridChunkRecord(
        chunk=chunk,
        parent_point_id=POINT_ID,
        chunk_index=0,
        chunk_count=1,
    )


@pytest.fixture
def vector():
    """1,024차원 테스트 벡터."""

    return [0.1] * DENSE_VECTOR_SIZE


def test_point_uuid_preserved(record, vector):
    """Qdrant Point ID가 청크 UUID와 일치한다."""

    point = build_qdrant_point(record, vector)

    assert str(point.id) == str(POINT_ID)


def test_dense_vector_dimension(record, vector):
    """Dense Vector는 1,024차원이다."""

    point = build_qdrant_point(record, vector)

    assert DENSE_VECTOR_NAME in point.vector

    dense = point.vector[DENSE_VECTOR_NAME]

    assert len(dense) == 1024
    assert dense == vector


def test_source_metadata_preserved(record, vector):
    """원본 문서 메타데이터를 유지한다."""

    point = build_qdrant_point(record, vector)

    payload = point.payload

    assert payload["source_id"] == "DOC-TEST-001"
    assert payload["source_type"] == "player_document"
    assert payload["case_id"] == "CASE-001"
    assert payload["family"] == "evidence"
    assert payload["incident_year"] == 2016


def test_access_policy_metadata_preserved(record, vector):
    """접근 정책 메타데이터를 유지한다."""

    point = build_qdrant_point(record, vector)

    payload = point.payload

    assert payload["policy_id"] == "POL-TEST-001"
    assert payload["access_scope"] == "collected_evidence"
    assert payload["character_id"] is None


def test_chunk_tracking_metadata(record, vector):
    """원본 UUID 및 청크 순서를 유지한다."""

    point = build_qdrant_point(record, vector)

    payload = point.payload

    assert payload["parent_point_id"] == str(POINT_ID)
    assert payload["chunk_index"] == 0
    assert payload["chunk_count"] == 1


def test_search_text_and_body_preserved(record, vector):
    """검색 텍스트와 원본 본문을 유지한다."""

    point = build_qdrant_point(record, vector)

    payload = point.payload

    assert payload["search_text"] == record.chunk.search_text
    assert payload["body"] == record.chunk.body
    assert payload["content_hash"] == record.chunk.content_hash


def test_internal_metadata_not_exposed(record, vector):
    """관리자 전용 메타데이터를 Payload에 포함하지 않는다."""

    point = build_qdrant_point(record, vector)

    forbidden = {
        "source_refs",
        "protected_fact_ids",
        "admin_truth",
        "supersedes",
        "stage_priority",
        "effects",
        "culprit",
        "solution",
    }

    assert not forbidden.intersection(point.payload)


def test_npc_metadata_preserved(record, vector):
    """NPC 지식 카드의 인물 정보를 유지한다."""

    npc_chunk = record.chunk.model_copy(
        update={
            "source_id": "K-C01-001",
            "source_type": "npc_knowledge",
            "family": "npc_knowledge",
            "access_scope": "character_only",
            "character_id": "C01",
        }
    )

    npc_record = replace(
        record,
        chunk=npc_chunk,
    )

    point = build_qdrant_point(npc_record, vector)

    assert point.payload["source_type"] == "npc_knowledge"
    assert point.payload["character_id"] == "C01"
    assert point.payload["access_scope"] == "character_only"


def test_original_record_not_modified(record, vector):
    """Point 변환 과정에서 원본을 수정하지 않는다."""

    original_chunk = record.chunk.model_dump()
    original_vector = vector.copy()

    build_qdrant_point(record, vector)

    assert record.chunk.model_dump() == original_chunk
    assert vector == original_vector


def test_numeric_vector_conversion(record):
    """정수 벡터도 실수로 변환할 수 있다."""

    point = build_qdrant_point(
        record,
        [1] * DENSE_VECTOR_SIZE,
    )

    dense = point.vector[DENSE_VECTOR_NAME]

    assert all(isinstance(value, float) for value in dense)


@pytest.mark.parametrize(
    "invalid_vector",
    [
        None,
        "invalid vector",
        123,
        {"value": 1},
    ],
)
def test_invalid_vector_type_rejected(record, invalid_vector):
    """숫자 시퀀스가 아닌 벡터를 거부한다."""

    with pytest.raises(
        TypeError,
        match="숫자 시퀀스",
    ):
        build_qdrant_point(record, invalid_vector)


@pytest.mark.parametrize(
    "size",
    [512, 768, 1023, 1025],
)
def test_invalid_vector_dimension_rejected(record, size):
    """1,024차원이 아닌 벡터를 거부한다."""

    with pytest.raises(
        ValueError,
        match="차원이 일치하지 않습니다",
    ):
        build_qdrant_point(
            record,
            [0.1] * size,
        )


@pytest.mark.parametrize(
    "invalid_value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_non_finite_vector_rejected(record, invalid_value):
    """NaN과 무한대 벡터를 거부한다."""

    with pytest.raises(
        ValueError,
        match="유효하지 않은 Dense Vector",
    ):
        build_qdrant_point(
            record,
            [invalid_value] * DENSE_VECTOR_SIZE,
        )


def test_zero_vector_rejected(record):
    """영벡터를 거부한다."""

    with pytest.raises(
        ValueError,
        match="영벡터",
    ):
        build_qdrant_point(
            record,
            [0.0] * DENSE_VECTOR_SIZE,
        )


def test_non_numeric_vector_rejected(record):
    """숫자로 변환할 수 없는 벡터를 거부한다."""

    with pytest.raises(
        ValueError,
        match="유효하지 않은 Dense Vector",
    ):
        build_qdrant_point(
            record,
            ["not-a-number"] * DENSE_VECTOR_SIZE,
        )


@pytest.mark.parametrize(
    ("chunk_index", "chunk_count"),
    [
        (-1, 1),
        (1, 1),
        (0, 0),
        (3, 2),
    ],
)
def test_invalid_chunk_position_rejected(
    record,
    vector,
    chunk_index,
    chunk_count,
):
    """잘못된 청크 순서와 개수를 거부한다."""

    invalid_record = replace(
        record,
        chunk_index=chunk_index,
        chunk_count=chunk_count,
    )

    with pytest.raises(
        ValueError,
        match="청크 순서 정보",
    ):
        build_qdrant_point(invalid_record, vector)


def test_invalid_record_type_rejected(vector):
    """잘못된 청크 객체 타입을 거부한다."""

    with pytest.raises(
        TypeError,
        match="HybridChunkRecord",
    ):
        build_qdrant_point("invalid record", vector)
